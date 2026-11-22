"""Settings → Audio: the I2S DAC/HAT selector (api_server.set_dac_hat).

An I2S HAT (HiFiBerry, Allo, IQaudio…) is not an ALSA card until its device-tree
overlay is loaded at boot, so this selector is a boot-config edit, not a runtime
output switch. The backend persists the choice to a conf file on the shared /data
/etc overlay (so it survives OTA) and patches config.txt on the boot FATs. The
FAT patching needs real block devices, so it is stubbed here; what is pinned is
the gating (Pi-only, not during an update), the validation, and the saved conf.

The feature ships in the shared core and is gated on hifi_platform.is_raspberry()
(it reports `supported: False` and refuses writes on x86), so these tests drive
the platform marker through api_server's imported hifi_platform module.
"""
import json
import os
import tempfile
import unittest

import api_server as a


CATALOGUE = {
    "_source": "test",
    "cards": [
        {"id": "hifiberry-dacplus", "name": "HiFiBerry DAC+", "dacchip": "PCM5122",
         "iface": "I2S", "overlay": "hifiberry-dacplus", "overlay_params": ""},
        {"id": "allo-boss", "name": "Allo Boss DAC", "dacchip": "PCM5122",
         "iface": "I2S", "overlay": "allo-boss-dac-pcm512x-audio",
         "overlay_params": "slave"},
        {"id": "some-usb", "name": "A USB DAC", "dacchip": "", "iface": "USB",
         "overlay": "", "overlay_params": ""},
    ],
}


class DacHatTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = self.tmp.name
        self.cards_file = os.path.join(root, 'dac-cards.json')
        with open(self.cards_file, 'w', encoding='utf-8') as f:
            json.dump(CATALOGUE, f)
        self.hat_file = os.path.join(root, 'etc', 'dac-hat.conf')

        self._saved = {}
        self._patch('DAC_CARDS_FILE', self.cards_file)
        self._patch('DAC_HAT_FILE', self.hat_file)
        a._dac_cards_cache = None
        self._set_platform(True)
        self._patch('_update_in_progress', lambda: False)
        # Pretend both boot FATs were patched, so we test the backend's own logic
        # and not mount/umount of real partitions.
        self.applied = []
        self._patch('_apply_dac_overlay_to_boot_fats',
                    lambda ov: (self.applied.append(ov) or (list(a.DAC_BOOT_PARTLABELS), [])))

    def tearDown(self):
        for name, value in self._saved.items():
            setattr(a, name, value)
        a.hifi_platform.is_raspberry = self._platform_saved
        a._dac_cards_cache = None
        self.tmp.cleanup()

    def _patch(self, name, value):
        self._saved[name] = getattr(a, name)
        setattr(a, name, value)

    def _set_platform(self, is_rpi):
        """Drive the shared platform marker the HAT code gates on. Saved once so
        tearDown restores the real hifi_platform.is_raspberry."""
        if not hasattr(self, '_platform_saved'):
            self._platform_saved = a.hifi_platform.is_raspberry
        a.hifi_platform.is_raspberry = lambda: is_rpi

    def _saved_conf(self):
        with open(self.hat_file, encoding='utf-8') as f:
            return dict(line.strip().split('=', 1) for line in f if '=' in line)

    # ── catalogue / gating ──────────────────────────────────────────
    def test_list_hides_non_i2s_cards(self):
        ids = [c['id'] for c in a.list_dac_hats()['cards']]
        self.assertIn('hifiberry-dacplus', ids)
        self.assertNotIn('some-usb', ids)   # USB stays in the runtime output picker

    def test_not_supported_off_pi(self):
        self._set_platform(False)
        out = a.list_dac_hats()
        self.assertFalse(out['supported'])
        self.assertEqual(out['cards'], [])

    def test_set_refused_off_pi(self):
        self._set_platform(False)
        out = a.set_dac_hat('hifiberry-dacplus')
        self.assertFalse(out['success'])
        self.assertFalse(os.path.exists(self.hat_file))

    def test_set_refused_during_update(self):
        a._update_in_progress = lambda: True
        out = a.set_dac_hat('hifiberry-dacplus')
        self.assertFalse(out['success'])
        self.assertFalse(os.path.exists(self.hat_file))

    # ── apply a valid card ──────────────────────────────────────────
    def test_set_valid_card_persists_and_patches(self):
        out = a.set_dac_hat('allo-boss')
        self.assertTrue(out['success'])
        self.assertTrue(out['reboot_required'])
        self.assertEqual(out['current'], 'allo-boss')
        conf = self._saved_conf()
        self.assertEqual(conf['id'], 'allo-boss')
        # overlay = driver + ',' + drvoptions
        self.assertEqual(conf['overlay'], 'allo-boss-dac-pcm512x-audio,slave')
        self.assertEqual(self.applied, ['allo-boss-dac-pcm512x-audio,slave'])

    def test_current_reflects_saved_choice(self):
        a.set_dac_hat('hifiberry-dacplus')
        self.assertEqual(a.list_dac_hats()['current'], 'hifiberry-dacplus')

    # ── clear / invalid ─────────────────────────────────────────────
    def test_none_clears_the_overlay(self):
        a.set_dac_hat('hifiberry-dacplus')
        out = a.set_dac_hat('none')
        self.assertTrue(out['success'])
        self.assertEqual(out['current'], '')
        self.assertEqual(self._saved_conf()['overlay'], '')
        self.assertEqual(self.applied[-1], '')   # empty overlay reaches the renderer

    def test_empty_clears_the_overlay(self):
        a.set_dac_hat('hifiberry-dacplus')
        out = a.set_dac_hat('')
        self.assertTrue(out['success'])
        self.assertEqual(self._saved_conf()['id'], '')

    def test_unknown_card_rejected(self):
        out = a.set_dac_hat('not-a-real-hat')
        self.assertFalse(out['success'])
        self.assertEqual(out['code'], 'dac.invalidCard')
        self.assertFalse(os.path.exists(self.hat_file))

    def test_patch_failure_surfaces(self):
        a._apply_dac_overlay_to_boot_fats = lambda ov: ([], ['hifi-boot-a (absent)'])
        out = a.set_dac_hat('hifiberry-dacplus')
        self.assertFalse(out['success'])
        self.assertEqual(out['code'], 'dac.applyFailed')


if __name__ == '__main__':
    unittest.main()
