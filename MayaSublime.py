import sublime, sublime_plugin
from telnetlib import Telnet
import time
import re
import os.path

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


class SendToMayaCommand(sublime_plugin.TextCommand):

    PY_CMD_TEMPLATE = textwrap.dedent('''
                                        import traceback
                                        import __main__
                                        try:
                                            exec(%r, __main__.__dict__, __main__.__dict__)
                                        except:
                                            traceback.print_exc()''')

    def run(self, edit):


        syntax = self.view.settings().get('syntax')

        if re.search(r'python', syntax, re.I):
            lang = 'python'
        elif re.search(r'mel', syntax, re.I):
            lang = 'mel'
        else:
            print 'No Maya Recognized Language Found'
            return

        host = _settings['hostname']
        port = _settings['python_port'] if lang == 'python' else _settings['mel_port']

        send_regions = self.view.sel()  # Returns type sublime.regions
        has_selection = any(not sel.empty() for sel in send_regions)
        snips = []

        if not has_selection:
            print "Nothing Selected, Attempting to Source/Import Current File"
            if self.view.is_dirty():
                sublime.error_message("Save Changes Before Maya Source/Import")
            else:
                file_path = self.view.file_name()
                if file_path is not None:
                    file_name = os.path.basename(file_path)
                    module_name = os.path.splitext(file_name)[0]

                    if lang == 'python':
                        snips.append('import {0}\nreload({0})'.format(module_name))
                    else:
                        snips.append('rehash; source {0};'.format(module_name))
                    #print "SNIPS:", snips

        for region in send_regions:
            selection = self.view.substr(region)
            snips.extend(line for line in selection.splitlines())

        mCmd = str('\n'.join(snips))
        if not mCmd:
            return

        print 'Sending:\n%s...\n' % mCmd[:200]

        if lang == 'python':
            mCmd = ("import traceback\n"
                    "import __main__\n"
                    "try:\n"
                    "    exec(%r, __main__.__dict__, __main__.__dict__)\n"
                    "except:\n"
                    "    traceback.print_exc()" % mCmd)

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
