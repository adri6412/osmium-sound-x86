package Plugins::OsmiumRecommended::Plugin;

# Osmium Recommended — surface the appliance's "Consigliati" list inside Lyrion,
# so it shows up in Material Skin (and the classic web UI and control apps), not
# only in the Qt kiosk.
#
# There is no recommendation engine here. The list is computed offline by the
# hifi-recommend job (hifi_recommend.py) and served as JSON by the appliance's
# own api_server on the loopback:
#
#   GET http://127.0.0.1:8000/recommendations
#     -> { state, items: [ { album, artist, cover, source, play_kind, play_id,
#                            tracks: [ { title, sub, dur, url }, ... ] }, ... ] }
#
# This plugin is a thin reader of that endpoint: it registers one home-screen
# "app" whose feed turns each recommendation into a playable Lyrion menu item.
#
#   * play_kind 'album_id' — a local-library album. Rendered with native actions
#     (browselibrary / playlistcontrol by album_id) so browse, play and add all
#     behave like any other library album, artwork included.
#   * play_kind 'url'      — a streaming-service album (Qobuz / Tidal / Deezer).
#     Rendered from the captured tracklist as a playlist of audio items; actual
#     playback needs the matching service plugin to be installed and logged in.
#
# When the list is empty or recommendations are off, the feed shows a single
# explanatory line instead of an error.

use strict;
use warnings;

use base qw(Slim::Plugin::OPMLBased);

use JSON::XS::VersionOneAndTwo;

use Slim::Utils::Log;
use Slim::Utils::Strings qw(cstring);
use Slim::Networking::SimpleAsyncHTTP;

use constant API_URL => 'http://127.0.0.1:8000/recommendations';

my $log = Slim::Utils::Log->addLogCategory({
	category     => 'plugin.osmiumrecommended',
	defaultLevel => 'WARN',
	description  => 'PLUGIN_OSMIUMRECOMMENDED',
});

sub initPlugin {
	my $class = shift;

	$class->SUPER::initPlugin(
		feed   => \&feed,
		tag    => 'osmiumrecommended',
		menu   => 'apps',
		is_app => 1,
		weight => 1,
	);
}

sub getDisplayName { 'PLUGIN_OSMIUMRECOMMENDED' }

# Home-screen app: no player context required to open it.
sub playerMenu { }

sub feed {
	my ($client, $cb, $args) = @_;

	Slim::Networking::SimpleAsyncHTTP->new(
		sub {
			my $http = shift;
			$cb->({ items => _parse($client, $http->content) });
		},
		sub {
			my $http = shift;
			$log->warn('recommendations fetch failed: ' . ($http->error || 'unknown'));
			$cb->({ items => [ _line($client, 'PLUGIN_OSMIUMRECOMMENDED_UNAVAILABLE') ] });
		},
		{ timeout => 15 },
	)->get(API_URL);
}

sub _parse {
	my ($client, $content) = @_;

	my $data = eval { from_json($content) };
	if ( $@ || ref $data ne 'HASH' ) {
		$log->warn('recommendations: bad JSON (' . ($@ || 'not an object') . ')');
		return [ _line($client, 'PLUGIN_OSMIUMRECOMMENDED_UNAVAILABLE') ];
	}

	my $state = $data->{state} || '';
	my $list  = $data->{items} || [];

	if ( $state ne 'ok' || ref $list ne 'ARRAY' || !@$list ) {
		my $key = $state eq 'disabled'  ? 'PLUGIN_OSMIUMRECOMMENDED_DISABLED'
		        : $state eq 'few_plays'  ? 'PLUGIN_OSMIUMRECOMMENDED_FEWPLAYS'
		        : $state eq 'never_run'  ? 'PLUGIN_OSMIUMRECOMMENDED_NEVERRUN'
		        :                          'PLUGIN_OSMIUMRECOMMENDED_EMPTY';
		return [ _line($client, $key) ];
	}

	return [ map { _album_item($_) } @$list ];
}

sub _line {
	my ($client, $token) = @_;
	return { name => cstring($client, $token), type => 'text' };
}

sub _album_item {
	my ($r) = @_;

	my $album  = $r->{album}  // '';
	my $artist = $r->{artist} // '';

	my $item = {
		name            => $album,
		line1           => $album,
		line2           => $artist,
		favorites_title => ( $artist ne '' ? "$album - $artist" : $album ),
	};

	if ( ($r->{play_kind} || '') eq 'album_id' && defined $r->{play_id} && $r->{play_id} ne '' ) {
		# Local-library album: hand straight back to the native library browse,
		# so Material Skin gets a real album (artwork, play/add, track menu).
		my $id = $r->{play_id};
		$item->{image}   = $r->{cover} ? "/music/$r->{cover}/cover" : undef;
		$item->{type}    = 'playlist';
		$item->{playall} = 1;
		$item->{actions} = {
			go => {
				command     => [ 'browselibrary', 'items' ],
				fixedParams => { mode => 'tracks', album_id => $id },
			},
			play => {
				command     => [ 'playlistcontrol' ],
				fixedParams => { cmd => 'load', album_id => $id },
			},
			add => {
				command     => [ 'playlistcontrol' ],
				fixedParams => { cmd => 'add', album_id => $id },
			},
		};
		return $item;
	}

	# Streaming album: build a playlist from the captured tracklist. The track
	# URLs are the service's own favourites/stream URLs and need that service
	# plugin installed to actually play.
	$item->{image} = $r->{cover} if $r->{cover};

	my @tracks;
	for my $t ( @{ $r->{tracks} || [] } ) {
		next unless ref $t eq 'HASH' && $t->{url};
		push @tracks, {
			name     => $t->{title},
			line1    => $t->{title},
			line2    => $t->{sub},
			type     => 'audio',
			url      => $t->{url},
			play     => $t->{url},
			duration => ( $t->{dur} ? $t->{dur} + 0 : undef ),
			image    => $r->{cover} || undef,
		};
	}

	if (@tracks) {
		$item->{type}    = 'playlist';
		$item->{playall} = 1;
		$item->{items}   = \@tracks;
	}
	elsif ( defined $r->{play_id} && $r->{play_id} ne '' ) {
		# No tracklist captured: fall back to the album URL. The service's own
		# protocol handler expands it into the album when played.
		$item->{type} = 'audio';
		$item->{url}  = $r->{play_id};
		$item->{play} = $r->{play_id};
	}
	else {
		$item->{type} = 'text';
	}

	return $item;
}

1;
