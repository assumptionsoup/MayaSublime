import sublime, sublime_plugin
from telnetlib import Telnet
import time
import sys
import os.path
import logging

SUPPORTED_LANGUAGES = ['python', 'mel']
_settings = {
    'hostname': '127.0.0.1',
    'mel_port': 7001,
    'python_port': 7002,

    # Possible future settings/features
    'on_selection': 'send_selection',  # send_line or send_file
    'on_send_file': 'import_file',  # execute file
    'use_temp_dir': True,  # saves current file to temp directory in the
                           # background, circumventing the need to save.
                           # Only works for execute file?
    # Need a way to send a specific file through a shortcut
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

class SendToMayaCommand(sublime_plugin.TextCommand):

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

        snips = self.get_selection()

        if snips:
            _logger.info('Attempting to send current selection.')
        else:
            _logger.info('Attempting to send current file.')

            # Check for unsaved changes
            if self.view.is_dirty():
                if sublime.ok_cancel_dialog('Save changes and send to Maya?', 'Save'):
                    self.view.run_command('save')
                else:
                    return

            file_path = self.view.file_name()
            if file_path is not None:
                file_name = os.path.basename(file_path)
                module_name = os.path.splitext(file_name)[0]

                if lang == 'python':
                    snips.append('import {0}\nreload({0})'.format(module_name))
                else:
                    snips.append('rehash; source {0};'.format(module_name))

        mCmd = str('\n'.join(snips))
        if not mCmd:
            return

        _logger.info('Sending:\n%s...\n', mCmd[:200])

        if lang == 'python':
            mCmd = ("import traceback\n"
                    "import __main__\n"
                    "try:\n"
                    "    exec(%r, __main__.__dict__, __main__.__dict__)\n"
                    "except:\n"
                    "    traceback.print_exc()" % mCmd)

        self.send_command(mCmd, _settings['hostname'], _settings['%s_port' % lang])

    def send_command(self, mCmd, host, port):
        '''Send the string mCmd to host:port using Telnet'''

        c = None
        try:
            c = Telnet(host, int(port), timeout=3)
            c.write(mCmd)
        except Exception, e:
            err = str(e)
            sublime.error_message(
                "Failed to communicate with Maya (%(host)s:%(port)s)):\n%(err)s" % locals()
            )
            raise
        else:
            time.sleep(.1)
        finally:
            if c is not None:
                c.close()

    def get_selection(self):
        '''Return current selection as a list of string source lines.
        Obey rules defined in _settings.'''

        selections = []
        if not _settings['on_selection'] == 'send_file':
            for region in self.view.sel():
                if _settings['on_selection'] == 'send_line':
                    region = self.view.line(region)

                substr = self.view.substr(region)
                selections.extend(line for line in substr.splitlines())
        return selections

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


settings_obj().clear_on_change("MayaSublime.settings")
settings_obj().add_on_change("MayaSublime.settings", sync_settings)
sync_settings()
