# CLI vs GUI Speed

> we really have to compare this to a gui app. We will find that some terminal commands are shorter and faster to type than the num of actions of an app open but most apps are actually faster if you consider each character as an action rather than word, and apps get faster over time too. The competetive difference in real world speed determines command line optimality or not and most commands actually fail to be competetive

---

## Analysis

Opening Slack: click icon, wait, click channel = 3 actions. `slack #channel` = 13+ keystrokes = 13+ actions. App wins.

Most CLI commands are verbose: `git commit -m "message"` = 20+ chars. A GUI commit button + text field is fewer total actions.

CLI only wins when:
- Commands are extremely short (`a 0`, `ls`)
- No equivalent GUI exists
- Automation/scripting is needed
- AI is typing, not humans

The `a` system targets that first case aggressively - single letters, numbers, minimal syntax. That's the narrow window where CLI actually beats GUI.
