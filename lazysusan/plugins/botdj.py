"""A set of LazySusan plugins that control the bot as a dj."""

import random
from lazysusan.helpers import (display_exceptions, admin_or_moderator_required,
                               no_arg_command, single_arg_command)
from lazysusan.plugins import CommandPlugin


def best_match(selection, options):
    """Return the best match from a set of options if possible.

    Return a list when there is not a single viable option.

    """
    if selection in options:
        return selection
    possibles = [x for x in options if x.startswith(selection)]
    if not possibles:
        return [x for x in options if selection in x]
    elif len(possibles) == 1:
        return possibles[0]
    else:
        return possibles


class Dj(CommandPlugin):

    """A plugin that controls whether or not the bot is dj-ing."""

    COMMANDS = {'/autoskip': 'auto_skip',
                '/djdown': 'stop',
                '/djup': 'play',
                '/skip': 'skip_song'}

    @property
    def should_step_down(self):
        """Return true if the bot should stop dj-ing."""
        return self.is_dj and (len(self.bot.listener_ids) <= 1
                               or len(self.bot.dj_ids) >= self.bot.max_djs)

    @property
    def should_step_up(self):
        """Return true if the bot should begin dj-ing."""
        return (not self.is_dj and len(self.bot.listener_ids) > 1
                and len(self.bot.dj_ids) < min(2, self.bot.max_djs - 1))

    @property
    def is_dj(self):
        """Return true if the bot is currently dj-ing."""
        return self.bot.bot_id in self.bot.dj_ids

    @property
    def is_playing(self):
        """Return true if the bot is currently playing a song."""
        return self.bot.bot_id == self.bot.api.currentDjId

    def __init__(self, *args, **kwargs):
        super(Dj, self).__init__(*args, **kwargs)
        self.end_song_step_down = False
        self.should_auto_skip = False
        self.register('add_dj', self.dj_update)
        self.register('deregistered', self.dj_update)
        self.register('endsong', self.end_song)
        self.register('newsong', self.new_song)
        self.register('registered', self.dj_update)
        self.register('rem_dj', self.dj_update)

    @no_arg_command
    def auto_skip(self, data):
        """Toggle whether the bot should play anything."""
        self.should_auto_skip = not self.should_auto_skip
        if self.should_auto_skip:
            self.bot.reply('I\'ll just keep this seat warm for you.', data)
            if self.is_playing and len(self.bot.dj_ids) > 1:
                self.bot.api.skip()
        else:
            self.bot.reply('I\'m back baby!', data)

    @display_exceptions
    def dj_update(self, data):
        """Handle callbacks affecting the users in the room and at the table.

        As a result, the bot may begin or stop dj-ing.

        """
        for user in data['user']:
            if self.bot.bot_id == user['userid']:
                if data['command'] == 'rem_dj':
                    self.should_auto_skip = False
                return  # Ignore updates from the bot

        if self.should_step_down:
            if self.is_playing:
                self.end_song_step_down = True
            else:
                print('Leaving the table')
                self.bot.api.remDj()
        elif self.should_step_up:
            print('Stepping up to dj')
            self.bot.api.addDj()

    def end_song(self, _):
        """Conditionally stop dj-ing at the end of a song."""
        if self.end_song_step_down:
            if self.should_step_down:
                print('Delayed leaving the table.')
                self.bot.api.remDj()
            self.end_song_step_down = False

    @display_exceptions
    def new_song(self, _):
        """Called when a new song starts playing."""
        num_djs = len(self.bot.dj_ids)
        if self.is_playing and self.should_auto_skip and num_djs > 1:
            self.bot.api.skip()

    @admin_or_moderator_required
    @no_arg_command
    def play(self, data):
        """Attempt to have the bot dj."""
        if self.is_dj:
            return self.bot.reply('I am already a dj.', data)
        if len(self.bot.dj_ids) < self.bot.max_djs:
            return self.bot.api.addDj()
        self.bot.reply('I can not do that right now.', data)

    @no_arg_command
    def skip_song(self, data):
        """Ask the bot to skip the current song"""
        if not self.is_playing:
            self.bot.reply('I am not currently playing.', data)
        else:
            self.bot.api.skip()
            self.bot.reply(':poop: I was just getting into it.', data)

    @admin_or_moderator_required
    @no_arg_command
    def stop(self, data):
        """Have the bot step down as a dj."""
        if not self.is_dj:
            return self.bot.reply('I am not currently dj-ing.', data)
        self.bot.api.remDj()


class Playlist(CommandPlugin):
    COMMANDS = {'/pladd': 'add',
                '/plavailable': 'available',
                '/playlists': 'list_playlists',
                '/plclear': 'clear',
                '/plcreate': 'create',
                '/pldelete': 'delete',
                '/pllist': 'list',
                '/plload': 'load',
                '/plshuffle': 'shuffle',
                '/plskip': 'skip_next',
                '/plswitch': 'switch',
                '/plupdate': 'update_playlist'}
    LIST_MAX_ITEMS = 5
    PLAYLIST_PREFIX = 'botplaylist.'
    UPDATE_MAX_ITEMS = 10
    UPDATE_MIN_LISTENERS = 5
    UPDATE_MIN_ROOMS = 20

    def __init__(self, *args, **kwargs):
        super(Playlist, self).__init__(*args, **kwargs)
        self.playlist = None
        self.playlists = {}
        self.register('roomChanged', self._room_init)
        self.room_list = {}
        # Fetch room info if this is a reload
        if self.bot.api.roomId:
            self.bot.api.roomInfo(self._room_init)

    def _room_init(self, _):
        """Initialization that must wait until connected to a room."""
        if not self.playlist:
            self.bot.api.playlistListAll(self._playlist_init)
        self.bot.api.listRooms(skip=0, callback=self.get_room_list(0))

    def _playlist_init(self, data):
        for item in data['list']:
            self.playlists[item['name']] = set()
            if item['active']:
                self.playlist = item['name']
        self.bot.api.playlistAll(self.playlist, self._playlist_info)

    def _playlist_info(self, data):
        self.playlists[self.playlist] = set(x['_id'] for x in data['list'])

    @no_arg_command
    def add(self, data):
        """Add the current song to the bot's default playlist."""
        if not self.bot.api.currentSongId:
            self.bot.reply('There is no song playing.', data)
            return
        playlist = self.playlists[self.playlist]
        if self.bot.api.currentSongId in playlist:
            self.bot.reply('We already have that song.', data)
        else:
            self.bot.reply('Cool tunes, daddio.', data)
            self.bot.api.playlistAdd('default', self.bot.api.currentSongId,
                                     len(playlist))
            if self.playlist == 'default':
                playlist.add(self.bot.api.currentSongId)
        self.bot.api.bop()

    @admin_or_moderator_required
    @no_arg_command
    def available(self, data):
        """Output the names of the available playlists (local)."""
        playlists = []
        for key in self.bot.config:
            if key.startswith(self.PLAYLIST_PREFIX):
                playlists.append(key[len(self.PLAYLIST_PREFIX):])
        reply = 'Available playlists: '
        reply += ', '.join(sorted(playlists))
        self.bot.reply(reply, data)

    @admin_or_moderator_required
    @no_arg_command
    def clear(self, data):
        """Clear the bot's current playlist."""
        def delete_callback(cb_data):
            def create_callback(cb_data2):
                if cb_data2['success']:
                    reply = 'Cleared playlist {0}.'.format(self.playlist)
                else:
                    reply = cb_data['err']
                self.bot.reply(reply, data)

            if cb_data['success']:
                self.playlists[self.playlist] = set()
                self.bot.api.playlistCreate(self.playlist, create_callback)
            else:
                self.bot.reply(cb_data['err'], data)

        if not self.playlists[self.playlist]:
            self.bot.reply('The playlist is already empty.', data)
        elif self.playlist != 'default':
            self.bot.api.playlistDelete(self.playlist, delete_callback)
        else:
            self.bot.api.playlistRemove(self.playlist, 0,
                                        self.clear_callback(data))

    def clear_callback(self, caller_data, complete_callback=None):
        @display_exceptions
        def _closure(data):
            if not data['success']:
                self.bot.reply('Failure clearing playlist. There are still '
                               '{0} items.'.format(len(playlist)),
                               caller_data)
                return
            playlist.remove(data['song_dict'][0]['fileid'])
            removed = original_count - len(playlist)
            if removed % 30 == 0:
                self.bot.reply('Removed {0} of {1} songs so far.'
                               .format(removed, original_count), caller_data)
            if playlist:  # While there are songs, continue to remove
                self.bot.api.playlistRemove(self.playlist, 0, _closure)
            elif complete_callback:  # Perform completion action
                complete_callback()
            else:
                self.bot.reply('Cleared playlist {0}.'.format(self.playlist),
                               caller_data)

        playlist = self.playlists[self.playlist]
        original_count = len(playlist)
        return _closure

    @single_arg_command
    def create(self, message, data):
        """Create a playlist with the provided name."""
        def callback(cb_data):
            if cb_data['success']:
                reply = 'Created playlist {0}.'.format(
                    cb_data['playlist_name'])
                self.playlists[message] = set()
            else:
                reply = cb_data['err']
            self.bot.reply(reply, data)
        self.bot.api.playlistCreate(message, callback)

    @single_arg_command
    def delete(self, message, data):
        """Delete a playlist with the provided name."""
        def callback(cb_data):
            if cb_data['success']:
                reply = 'Deleted playlist {0}'.format(cb_data['playlist_name'])
                del self.playlists[message]
            else:
                reply = cb_data['err']
            self.bot.reply(reply, data)
        self.bot.api.playlistDelete(message, callback)

    def get_room_list(self, skip):
        @display_exceptions
        def _closure(data):
            count = skip
            for room, _ in data['rooms']:
                if room['chatserver'] != self.bot.api.roomChatServer:
                    continue
                count += 1
                if room['metadata']['listeners'] < self.UPDATE_MIN_LISTENERS \
                        and count > self.UPDATE_MIN_ROOMS:
                    break
                self.room_list[room['shortcut']] = room['roomid']
            else:
                # Python closures are read-only so we have to recreate
                self.bot.api.listRooms(skip=count,
                                       callback=self.get_room_list(count))
                return
        return _closure

    @no_arg_command
    def list(self, data):
        """Output a summary of the songs in the current playlist."""
        @display_exceptions
        def callback(cb_data):
            preview = []
            playlist = set()
            for item in cb_data['list']:
                playlist.add(item['_id'])
                artist = item['metadata']['artist'].encode('utf-8')
                song = item['metadata']['song'].encode('utf-8')
                item = '"{0}" by {1}'.format(song, artist)
                if len(preview) < self.LIST_MAX_ITEMS:
                    preview.append(item)
            reply = ('There are {0} songs in the playlist. '
                     .format(len(playlist)))
            if preview:
                reply += 'The first {0} are: {1}'.format(len(preview),
                                                         ', '.join(preview))
            self.playlists[self.playlist] = playlist
            self.bot.reply(reply, data)
        self.bot.api.playlistAll(self.playlist, callback)

    @no_arg_command
    def list_playlists(self, data):
        """List the available playlists."""
        @display_exceptions
        def callback(cb_data):
            def display(name):
                return name if name != self.playlist else name + '*'
            reply = 'Available playlists: {0}'.format(
                ', '.join(display(x['name']) for x in
                          sorted(cb_data['list'], key=lambda x: x['name'])))
            self.bot.reply(reply, data)
        self.bot.api.playlistListAll(callback)

    @admin_or_moderator_required
    @single_arg_command
    def load(self, message, data):
        """Load the specified local playlist into a new playlist."""
        def add_songs(cb_data=None):
            if cb_data and cb_data['success']:
                failed.pop(0)
            playlist = self.playlists[playlist_name]
            while song_ids:
                song_id = song_ids.pop(0)
                failed.insert(0, song_id)  # Removed on success
                if song_id not in playlist:
                    playlist.add(song_id)
                    self.bot.api.playlistAdd(playlist_name, song_id,
                                             len(playlist) - 1, add_songs)
                    break
            else:
                self.bot.api.playlistSwitch(playlist_name, switch_callback)

        def create_callback(cb_data):
            if cb_data['success']:
                self.playlists[playlist_name] = set()
                add_songs()
            else:
                self.bot.reply(cb_data['err'], data)

        def delete_callback(cb_data):
            if cb_data['success']:
                del self.playlists[playlist_name]
                self.bot.api.playlistCreate(playlist_name, create_callback)
            else:
                self.bot.reply(cb_data['err'], data)

        def switch_callback(cb_data):
            if cb_data['success']:
                self.playlist = cb_data['playlist_name']
                reply = ('Loaded {0} songs from local playlist {1}.'
                         .format(len(self.playlist), message))
                if failed:
                    reply += (' Failed to load the following song ids: {0}'
                              .format(','.join(failed)))
            else:
                reply = cb_data['err']
            self.bot.reply(reply, data)

        config_name = '{0}{1}'.format(self.PLAYLIST_PREFIX, message)
        if config_name not in self.bot.config:
            self.bot.reply('Playlist `{0}` does not exist.'
                           .format(config_name), data)
            return

        song_ids = self.bot.config[config_name].split('\n')
        failed = []
        playlist_name = 'local_{0}'.format(message)
        if playlist_name in self.playlists:  # Delete the playlist
            self.bot.api.playlistDelete(playlist_name, delete_callback)
        else:  # Create the playlist
            self.bot.api.playlistCreate(playlist_name, create_callback)

    @no_arg_command
    def shuffle(self, data):
        """Randomly select the next 10 songs in the bot's current playlist."""
        def get_endpoints():
            dst = index[0]
            index[0] += 1
            item = new_order.pop(0)
            src = original.index(item)
            if src != dst:  # Reorder for next use
                del original[src]
                original.insert(dst, item)
            return src, dst

        def callback(cb_data):
            if not cb_data['success']:
                self.bot.reply('Error shuffling playlist.', data)
            elif index[0] >= num:
                self.bot.reply('Everyday I\'m shuffling (completed).', data)
            else:
                src, dst = get_endpoints()
                self.bot.api.playlistReorder(self.playlist, src, dst, callback)

        # We don't actually keep track of the song order so just use their
        # current indexes
        original = list(range(len(self.playlists[self.playlist])))
        num = min(len(original), 10)
        if num < 2:
            self.bot.reply('There are too few items to shuffle in {0}.'
                           .format(self.playlist), data)
            return
        new_order = random.sample(original, num)
        index = [0]  # Needs to be a list in order to mutate
        src, dst = get_endpoints()
        self.bot.api.playlistReorder(self.playlist, src, dst, callback)

    @no_arg_command
    def skip_next(self, data):
        """Skip the next song in the bot's current playlist.

        Note: This will not affect the currently playing song.

        """
        def callback(cb_data):
            if cb_data['success']:
                self.bot.reply('Next song skipped.', data)
            else:
                self.bot.reply('Error skipping next song.', data)
        self.bot.api.playlistReorder(self.playlist, 0,
                                     len(self.playlists[self.playlist]) - 1,
                                     callback)

    @single_arg_command
    def switch(self, message, data):
        """Switch to the specified playlist."""
        def callback(cb_data):
            if cb_data['success']:
                self.playlist = cb_data['playlist_name']
                reply = 'Switched to playlist {0}'.format(self.playlist)
                self.bot.api.playlistAll(self.playlist, self._playlist_info)
            else:
                reply = cb_data['err']
            self.bot.reply(reply, data)
        selection = best_match(message, self.playlists.keys())
        if not selection:
            self.bot.reply('Invalid playlist name.', data)
        elif isinstance(selection, list):
            self.bot.reply('Possible playlist matches: {0}'
                           .format(', '.join(selection)), data)
        else:
            self.bot.api.playlistSwitch(selection, callback)

    @single_arg_command
    def update_playlist(self, message, data):
        """Update the room playlist from songs played in the provideded room.

        This will (create and) update a playlist specific to the provided
        room. Upon completion, the bot will switch to this playlist.

        """
        def room_info_callback(cb_data):
            def add_songs():
                def add_song_callback(_):
                    if to_add:
                        _, song_id = to_add.pop(0)
                        playlist.add(song_id)
                        self.bot.api.playlistAdd(self.playlist, song_id, 0,
                                                 add_song_callback)
                    else:
                        self.bot.reply('Added {0} songs'.format(num), data)

                playlist = self.playlists[self.playlist]
                songs = cb_data['room']['metadata']['songlog']

                to_add = []
                for song in songs:
                    if song['_id'] not in playlist:
                        to_add.append((song.get('score'), song['_id']))
                if not to_add:
                    self.bot.reply('No songs to add.', data)
                    return

                # Most popular songs will play first (added last)
                to_add.sort()
                num = len(to_add)
                add_song_callback(None)

            def list_callback(cb_data2):
                self.playlists[self.playlist] = set(x['_id'] for x in
                                                    cb_data2['list'])
                add_songs()

            def switch_callback(cb_data2):
                if cb_data2['success']:
                    self.playlist = cb_data2['playlist_name']
                    self.bot.api.playlistAll(self.playlist, list_callback)
                else:
                    self.bot.reply(cb_data2['err'], data)

            def create_callback(cb_data2):
                if cb_data2['success']:
                    self.bot.api.playlistSwitch(message, switch_callback)
                else:
                    self.bot.reply(reply, cb_data2['err'])

            if message not in self.playlists:  # Create the playlist
                self.bot.api.playlistCreate(message, create_callback)
            elif message == self.playlist:  # Add songs
                add_songs()
            else:  # Switch to the playlist
                self.bot.api.playlistSwitch(message, switch_callback)

        selection = best_match(message, self.room_list.keys())
        if not selection:
            reply = 'Could not find `{0}` in the room_list. '.format(message)
            reply += 'Perhaps try one of these: '
            reply += ', '.join(sorted(random.sample(self.room_list,
                                                    self.UPDATE_MAX_ITEMS)))
            self.bot.reply(reply, data)
        elif isinstance(selection, list):
            self.bot.reply('Possible room matches: {0}'
                           .format(', '.join(selection)), data)
        else:
            message = selection
            room_id = self.room_list[message]
            self.bot.reply('Querying {0} ({1})'.format(message, room_id), data)
            self.bot.api.roomInfo(room_info_callback, room_id=room_id)
