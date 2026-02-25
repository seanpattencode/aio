# Job Pipeline — Capture to Review

## Original (Feb 25 2025, verbatim)

a isn't doing enough work. I must launch more work. a jobs can do this but i don't really use it enough. I need a really really easy way to add a job from anywhere that takes almost no time. But then i also need an equally painless way to review. a job probably should integrate with review. the reason i don't use it, i have to figure out. maybe i need to shorten to a j to match a c, i use a c all the time. I guess often i use a c to launch jobs in real time with visibility but jobs don't have visibility as easily. The question is why does a jobs exist when i can real time a c. One main reason is to launch jobs on different devices to do more. but decision of which device goes where is annoying and on that device it doesn't show instantly. I guess i need a simple interface to super quickly open a view of a running job. But maybe even thats not enough? maybe i need a way to actually run job on monitors i have open.

Stop. You're exploring requirements right now, not coding. That's fine — but notice the scream just crystallized:
"a c gives me visibility. a job doesn't. So I use a c instead of scaling."
The inadequacy isn't job launching or device routing or monitor control. It's that jobs are invisible by default.

many panels get hard to read. I suppose simple solution is "window" of tmux?

Right. a c splits a pane. a j creates a new tmux window. Full screen, easy to flip between with tmux hotkeys.

a job should probably have .done file as ending method
maybe each a job should email when done so i am native notification with easy resume attach
show jobs active on different devices in one place

start aggressively delegating to agents and auto accepting more things to dev faster set one day if i don't like it just revert

have an ai job system that marks my notes or tasks as provisionally complete i can then mark as archived for later

or maybe have a shadow ai version of my projects separate from what i approve and i merge things in piece by piece

Maybe I can just batch notes and tasks together, call a claude agent, with context, then have it spawn jobs and mark notes and tasks with job information and then i review jobs and can dismiss notes and tasks too if they satisfy and review them from notes and tasks

i want extraction but llm is doing lossy compression unless i specify preserve original plus explanation/refinement

notes needs input box in terminal like e editor

## Context

The core diagnosis: `a c` is used because it's VISIBLE (split pane, you see it). `a j` (jobs) is NOT visible, so it goes unused. This means Sean can't scale past what he can watch in real time.

Solution identified: `a j` opens tmux WINDOW (not pane) — full screen, flip with hotkeys like browser tabs. Already partially implemented in cmd_j.

Pipeline needed: notes/tasks → batch process → spawn jobs → jobs notify on completion → review from unified view → dismiss/merge.

Key features still needed:
1. .done file detection for job completion
2. Email/notification on done
3. Cross-device job visibility in one place
4. Notes → jobs batch conversion
5. Terminal input box for notes (like `e` editor)
6. Review integration from job list
