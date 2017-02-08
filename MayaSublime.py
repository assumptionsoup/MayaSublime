import collections
import logging
import os
import platform
import queue
import socket
import sys
import threading
import time

import sublime
import sublime_plugin

_ST3 = int(sublime.version()) >= 3000

PLATFORM = platform.system()
SUPPORTED_LANGUAGES = ['python', 'mel']
_settings = {
    'hostname': '127.0.0.1',
    'mel_port': 7001,
    'python_port': 7002,
    'on_selection': 'send_selection',  # send_line or send_file
    'on_send_file': 'import_file',  # execute_file
    'print_results': True,

    # Possible future settings/features
    # Identifying phrases which indicate a file is a python plugin.
    # Requires a 2 dimensional list, which is equivalent to (('A' AND 'B') OR ('C' AND 'D')
    'python_plugin_identifiers': (('def initializePlugin', 'def uninitializePlugin'),
                                  ('NODE_NAME', 'NODE_ID', 'NODE_CLASS')),
    'use_temp_dir': True,  # saves current file to temp directory in the
                           # background, circumventing the need to save.
                           # Only works for execute file?
    # Need a way to send a specific file through a shortcut?
}

# Create one logger only.
try:
    _logger
except:
    # Loggers are surprisingly verbose to set up
    _logger = logging.getLogger(__name__)
    _logger.setLevel(logging.INFO)
    hdlr = logging.StreamHandler(sys.stdout)
    fmtr = logging.Formatter("%(name)s: %(levelname)s: %(message)s")
    hdlr.setFormatter(fmtr)
    _logger.addHandler(hdlr)


def get_time():
    '''Get the most accurate time for the given os'''
    if platform == 'Windows':
        return time.clock()
    else:
        return time.time()


class AppendOutputCommand(sublime_plugin.TextCommand):
    def run(self, edit, text):
        self.view.insert(edit, self.view.size(), text)


class SendToMayaCommand(sublime_plugin.TextCommand):
    def __init__(self, *args, **kwargs):
        self.output_queue = queue.Queue()
        self.output_panel_name = 'MayaSublime'
        self.output_search_dir = None
        self.output_window = None
        self.output_view = None
        super(SendToMayaCommand, self).__init__(*args, **kwargs)

    def run(self, edit):
        # Find current document language with case insensitive search.
        syntax = self.view.settings().get('syntax')
        lang = next((lang for lang in SUPPORTED_LANGUAGES
                     if lang in syntax.lower()), None)
        if lang is None:
            _logger.info('No recognized language found!')
            return

        # Make sure there is a port for that language
        if '%s_port' % lang not in _settings:
            _logger.info('No port defined for %s language!', lang)
            return

        # Get list of lines to send to Maya
        if _settings['on_selection'] == 'send_file':
            source_lines = self.get_file(lang)
        else:
            whole_lines = _settings['on_selection'] == 'send_line'
            source_lines = self.get_selection(whole_lines=whole_lines)
            if not source_lines:
                source_lines = self.get_file(lang)

        if not source_lines:
            return

        # Maya expects \n, not os specific line breaks
        mCmd = str('\n'.join(source_lines))
        _logger.debug('Sending:\n%s...\n', mCmd)

        if lang == 'python':
            mCmd = ("import sublime_maya_interface\n"
                    "sublime_maya_interface.execute_sublime_code(%r, %r)" %
                    (mCmd, self.view.file_name() or ''))

        self.send_command(mCmd, _settings['hostname'],
                          _settings['%s_port' % lang])

    def send_command(self, mCmd, host, port):
        '''Send the string mCmd to Maya using host:port'''

        self.clear_output()
        connection = None
        if _ST3:
            mCmd = bytes(mCmd, 'utf-8')
        else:
            mCmd = bytes(mCmd)

        try:
            connection = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            connection.settimeout(3)
            connection.connect((host, port))
            connection.send(mCmd)
            if _settings['print_results']:
                self.print_response(connection)
        except Exception as e:
            err = str(e)
            sublime.error_message(
                ("Failed to communicate with Maya "
                 "(%(host)s:%(port)s)):\n%(err)s") % locals()
            )
            raise
        finally:
            if connection is not None and not _settings['print_results']:
                _logger.debug('Closing connection')
                connection.shutdown(socket.SHUT_RDWR)
                connection.close()

    def print_response(self, connection):
        '''Create a separate thread to print Maya's response'''

        def print_response():
            response_count = 0
            while True:
                try:
                    response = connection.recv(8192)
                except socket.timeout:
                    break

                if response:
                    response_count += 1
                    response = response.decode('utf-8')
                    # Maya calls this the "response terminator" and
                    # inserts it on every line. I call it "annoying".
                    response = response.replace('\n\x00', '')

                    # Maya likes sending "None" as it's first
                    # response to anything. I don't know why.
                    if response_count == 1 and response == 'None':
                        continue

                    self.output_queue.put(response)
                    # Use this callback to avoid flickering when quickly
                    # updating to the queue
                    sublime.set_timeout(self.display_output, 0.05)
                else:
                    # If the socket dies, we'll end up here.
                    break

                time.sleep(0.1)

        def run_in_thread():
            try:
                print_response()
                _logger.info('Done listening.')
            finally:
                connection.shutdown(socket.SHUT_RDWR)
                connection.close()

        # Start the thread
        threading.Thread(target=run_in_thread).start()

    def init_output_panel(self):
        if not self.view:
            return

        file_name = self.view.file_name()
        if file_name is None:
            working_dir = ''
        else:
            # Default the to the current files directory
            working_dir = os.path.dirname(file_name)

        if self.output_search_dir == working_dir:
            return
        else:
            self.output_search_dir = working_dir

        self.output_window = self.view.window()
        if not self.output_view:
            self.output_view = self.output_window.get_output_panel(
                self.output_panel_name)

        self.output_view.set_syntax_file('Packages/Python/Python.tmLanguage')

        # This regex magic is what makes tracebacks clickable
        output_settings = self.output_view.settings()
        output_settings.set("result_file_regex", '^\s+?File \"<(.*?)>\", line ([0-9]+)')
        output_settings.set("result_line_regex", 'line ([0-9]+)')
        output_settings.set("result_base_dir", self.output_search_dir)

        # Call get_output_panel a second time after assigning the above
        # settings, so that it'll be picked up as a result buffer
        self.output_window.get_output_panel(self.output_panel_name)

    def clear_output(self):
        # This is a bit of a hack.  I'm clearing the cache which informs
        # init_output_panel that it needs to make a new window with
        # correct regex.  Instead of "clearing" the output, I'm forcing
        # a new panel to be created.
        self.output_search_dir = None

    def display_output(self):
        if self.output_queue.empty():
            return

        if not self.view:
            return

        self.init_output_panel()

        # Write this text to the output panel and display it
        result = self.output_queue.get()
        _logger.info('Results: %s' % result)
        self.output_view.run_command('append_output', {'text': result})


        # Scroll view to end, placing the last line at the bottom of the
        # panel
        layout_height = self.output_view.layout_extent()[1]
        viewpoert_height = self.output_view.viewport_extent()[1]
        offset = layout_height - viewpoert_height
        self.output_view.set_viewport_position((0, offset), False)

        # Show view
        self.output_window.run_command(
            "show_panel", {"panel": "output.%s" % self.output_panel_name})

    def get_selection(self, whole_lines=False):
        '''
        Return current selection as a list of string source lines.
        '''

        # Store lines in map of {line_number: line_string}
        selected_lines = collections.defaultdict(str)
        for region in self.view.sel():
            if whole_lines:
                region = self.view.line(region)

            # Find the range of line indices that is selected in this region
            numberRange = self.get_lines_from_region(region)
            if numberRange is None:
                continue

            substr = self.view.substr(region)
            lines = substr.splitlines()

            # Match line number to line contents, and add to selected_lines
            assert len(lines) == len(numberRange)
            for line_number, line in zip(numberRange, lines):
                # Always append to the line, in case a multi-selection
                # is on the same line
                selected_lines[line_number] += line

        if selected_lines:
            _logger.debug('Attempting to send current selection.')
            file_region = sublime.Region(0, self.view.size())
            last_line, col = self.view.rowcol(file_region.end())
            selections = [selected_lines[x] for x in range(last_line + 1)]
        else:
            selections = []

        return selections

    def get_lines_from_region(self, region):
        if region.begin() == region.end():
            return None

        start_line, start_col = self.view.rowcol(region.begin())
        end_line, end_col = self.view.rowcol(region.end())

        # Remove the last line if the cursor is at the start of the line
        # (and therefore nothing is selected)
        end_line_region = self.view.line(region.end())
        if end_line_region.begin() == region.end():
            end_line -= 1
        return range(start_line, end_line + 1)

    def get_file(self, lang):
        """
        Return list of strings needed to source the current file.
        Obeys rules defined in _settings
        """
        _logger.debug('Attempting to send current file.')
        source_lines = []
        if _settings['on_send_file'] == 'execute_file':
            file_region = sublime.Region(0, self.view.size())
            source_lines = self.view.substr(file_region)
            source_lines = source_lines.splitlines()
        else:
            # Check for unsaved changes / Prompt to save if so
            if self.view.is_dirty():
                if sublime.ok_cancel_dialog('Save changes and send to Maya?', 'Save'):
                    self.view.run_command('save')
                else:
                    return

            # Get file path
            file_path = self.view.file_name()
            if file_path is not None:
                file_name = os.path.basename(file_path)
                module_name = os.path.splitext(file_name)[0]

                if lang == 'python':
                    source_line = 'import {0}\nreload({0})'.format(module_name)
                else:
                    source_line = 'rehash; source {0};'
                source_lines.append(source_line)
        return source_lines


def settings_obj():
    return sublime.load_settings("MayaSublime.sublime-settings")


def sync_settings():
    global _settings
    so = settings_obj()

    # Set global settings if they exist
    for key in _settings.keys():
        value = so.get('maya_%s' % key)
        if value is not None:
            _settings[key] = value


def plugin_loaded():
    settings_obj().clear_on_change("MayaSublime.sublime-settings")
    settings_obj().add_on_change("MayaSublime.sublime-settings", sync_settings)
    sync_settings()

if not _ST3:
    plugin_loaded()
