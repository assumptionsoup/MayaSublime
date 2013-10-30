import sublime, sublime_plugin
from telnetlib import Telnet
import time
import sys
import os
import logging
import threading
import platform
from contextlib import contextmanager

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
    text_to_output = []
    selected_lines = []

    def run(self, edit):
        # Find current document language with case insensitive search.
        syntax = self.view.settings().get('syntax')
        lang = next((lang for lang in SUPPORTED_LANGUAGES if lang in syntax.lower()), None)
        if lang is None:
            _logger.info('No recognized language found!')
            return

        # Make sure there is a port for that language
        if '%s_port' % lang not in _settings.keys():
            _logger.info('No port defined for %s language!', lang)
            return

        # Get list of lines to send to Maya
        source_lines = self.get_selection()
        if source_lines:
            _logger.info('Attempting to send current selection.')
        else:
            _logger.info('Attempting to send current file.')
            source_lines = self.get_file(lang)

        if not source_lines:
            return

        # Maya expects \n, not os specific line breaks
        mCmd = str('\n'.join(source_lines))

        _logger.info('Sending:\n%s...\n', mCmd[:200])

        if lang == 'python':
            file_name = self.view.file_name()
            if file_name:
                file_name = file_name.split('/')[-1]
                file_name = file_name.split('\\')[-1]
                file_name = '<%s>' % file_name
            else:
                file_name = '<untitled>'
            mCmd = ("import sublime_maya_interface\n"
                    "reload(sublime_maya_interface)\n"
                    "sublime_maya_interface.execute_sublime_code(%r, %r, %r)" %
                    (mCmd, file_name, self.selected_lines))

        self.send_command(mCmd, _settings['hostname'], _settings['%s_port' % lang])

    def is_python_plugin(self, file_contents):
        pass

    def send_command(self, mCmd, host, port):
        '''Send the string mCmd to Maya using host:port'''
        connection = None
        mCmd = bytes(mCmd, 'utf-8')
        try:
            connection = Telnet(host, int(port), timeout=10)
            connection.write(mCmd)
            if _settings['print_results']:
                self.print_response(connection, 3)
        except Exception as e:
            err = str(e)
            sublime.error_message(
                "Failed to communicate with Maya (%(host)s:%(port)s)):\n%(err)s" % locals()
            )
            raise
        finally:
            if connection is not None and not _settings['print_results']:
                _logger.info('closing connection')
                connection.close()

    def print_response(self, connection, timeout):
        '''Create a separate thread to print Maya's response'''

        def print_response_thread():
            start_time = get_time()
            try:
                while get_time() - start_time <= timeout:
                    try:
                        response = connection.read_very_eager()
                    except EOFError:
                        # Connection is closed
                        break
                    except AttributeError:
                        pass

                    if response:
                        response = response.decode('utf-8')
                        start_time = get_time()
                        # Maya really likes extra newlines.
                        seperator = '\n\n\n'
                        response = response.replace(seperator, '\n')
                        response = response.replace('None', '', 1)  # Maya likes sending the string 'None' first.
                        response = response.strip()
                        _logger.info('RESULTS:\n>%s\n' % '\n> '.join(response.splitlines()))
                        if response:
                            self.append_line_to_output(response)

                        # Reset timer.
                        sublime.set_timeout(self.display_output, 0)
                self.text_to_output = []
                _logger.info('Done listening.')
            finally:
                connection.close()

        # Start the thread
        threading.Thread(target=print_response_thread).start()

    def append_line_to_output(self, text):
        self.text_to_output.append(text)
        sublime.set_timeout(self.display_output, 0)

    def display_output(self, panel_name='MayaSublime'):
        if not self.text_to_output:
            return

        # Default the to the current files directory
        if not self.view:
            return

        file_name = self.view.file_name()
        if file_name is None:
            file_name = '<untitled>'

        win = self.view.window()
        if not hasattr(self, 'output_view'):
            self.output_view = win.get_output_panel(panel_name)

        view = self.output_view
        working_dir = os.path.dirname(file_name)

        self.output_view.set_syntax_file('Packages/Python/Python.tmLanguage')
        self.output_view.settings().set("result_file_regex", '^[ ]+File \"<(...*?)>\", line ([0-9]+)')
        self.output_view.settings().set("result_line_regex", 'line ([0-9]+)')
        self.output_view.settings().set("result_base_dir", working_dir)

        # Call get_output_panel a second time after assigning the above
        # settings, so that it'll be picked up as a result buffer
        win.get_output_panel(panel_name)

        # Write this text to the output panel and display it
        view.run_command('append_output', {'text': '\n'.join(self.text_to_output)})

        # Show window
        view.show(view.size())
        win.run_command("show_panel", {"panel": "output.%s" % panel_name})

    def get_selection(self):
        '''Return current selection as a list of string source lines.
        Obey rules defined in _settings.'''

        selections = []
        selected_lines = []
        if not _settings['on_selection'] == 'send_file':
            for region in self.view.sel():
                if _settings['on_selection'] == 'send_line':
                    region = self.view.line(region)

                lines = self.get_lines_from_region(region)
                if lines:
                    selected_lines.append(lines)
                substr = self.view.substr(region)
                selections.extend(line for line in substr.splitlines())

        # Collapse overlapping selected lines and save
        # self.selected_lines as a list of ranges
        self.selected_lines = []
        skip = 0
        for x, region in enumerate(selected_lines):
            if skip:
                skip = 0
                continue

            if x + 1 < len(selected_lines):
                if region[1] == selected_lines[x + 1][0]:
                    region = [region[0], selected_lines[x + 1]]
                    skip = 1
            self.selected_lines.append(range(region[0], region[1] + 1))

        return selections

    def get_lines_from_region(self, region):
        if region.begin() == region.end():
            return None

        start_line, start_col = self.view.rowcol(region.begin())
        end_line, end_col = self.view.rowcol(region.end())
        end_line_region = self.view.line(region.end())
        if end_line_region.begin() == region.end():
            # end line has no width!
            end_line -= 1

        return start_line + 1, end_line + 1

    def get_file(self, lang):
        '''Return list of strings needed to source file the current
        file.  Obeys rules defined in _settings'''

        source_lines = []
        self.selected_lines = []
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

def plugin_loaded()
    settings_obj().clear_on_change("MayaSublime.sublime-settings")
    settings_obj().add_on_change("MayaSublime.sublime-settings", sync_settings)
    sync_settings()
