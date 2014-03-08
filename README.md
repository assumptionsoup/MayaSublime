# MayaSublime
### A Sublime Text 2/3 plugin

Send selected MEL/Python code snippets or whole files to Maya via commandPort

----------

### Installation

1. clone this repo into the `SublimeText -> Preference -> Browse Packages` directory:
`git clone git://github.com/assumptionsoup/MayaSublime.git`

2. Copy the scripts in the MayaScripts folder to a script folder in Maya's Path.

3. Open a commandPort from your userScripts.mel or userScripts.py.  See `Usage` for more details.

4. Edit the `MayaSublime.sublime-settings` file, setting the port to match the commandPorts you have configured in Maya

5. By default Sublime Text maps the `ctrl+enter` hotkey to the Add Line macro. You may wish to edit the Sublime Text's
keymap file or Maya Sublime's keymap file to something else.

### Usage

To send a snippet, simply select some code in a mel or python script, and hit `ctrl+return`, or right click and choose "Send To Maya".
To send the current file, do the same without a selection. This will source or import/reload the file if it is on your Maya path.
A socket connection will be made to a running Maya instance on the configured port matching mel or python, and the code will be
run in Maya's environment.

As an example, if you want to open a commandPort on port 7002 for python (the default port in the config), you can do the following:

```python
# if it was already open under another configuration
cmds.commandPort(name=":7002", close=True)

# now open a new port
cmds.commandPort(name=":7002", sourceType="python")

# or open some random MEL port (make sure you change it to this port in your config file)
cmds.commandPort(name=":10000", sourceType="mel")

# to open default ports on maya startup add these to your userSetup.py
if not cmds.commandPort(':7001', q=True):
    cmds.commandPort(n=':7001', sourceType="mel")

if not cmds.commandPort(':7002', q=True):
    cmds.commandPort(n=':7002', sourceType="python")

```
