# Waiting Games for Claude Code (VS Code companion)

Companion to the [waiting-games plugin](https://github.com/shaico92/claude-waiting-games).
With it, the game opens as a terminal in VS Code's **bottom panel** while Claude Code works
(instead of a separate window), and **Enter** in the game puts you back in the Claude chat.

It has no commands and no settings. Once it is running, the plugin's hook finds it by itself;
without it the plugin keeps opening the game in its own window.

Install (needs `code` on the PATH): `python3 install.py vscode` in a clone of the repo,
then run **Developer: Reload Window**. Remove: `python3 install.py vscode-uninstall`.

How it works: it writes a small presence file to `<temp>/claude-games-vscode/` every 2 s and
watches that folder for requests from the hook (open the game, bring it forward) and from
the game (focus the chat, via the Claude Code extension's `claude-vscode.focus` command).
Nothing leaves your machine.
