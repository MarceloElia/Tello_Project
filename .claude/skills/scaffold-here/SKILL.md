---
name: scaffold-here
description: Scaffold the standard professional Python project layout directly into the current directory — no prompts, no nested folder, git initialized. Use for "scaffold this repo", "new project here", "set up this folder", "/scaffold-here".
---

Run exactly this, then report the result:

```bash
bash ~/.claude/scaffold_here.sh
```

Rules — do NOT deviate (this skill exists to be fast and cheap):
- Do NOT ask for a name or description. The script defaults the name to the current
  folder (kebab-cased) and uses a placeholder description.
- Do NOT read the template/script contents into context.
- Do NOT move files, flatten, or run git yourself — the script does all of it
  (scaffold in place, flatten the nested folder, `git init` + initial commit).
- To override defaults: `bash ~/.claude/scaffold_here.sh <name> "<description>"`.

After it runs, in one short line report the project path and the venv/install step
the script printed. Nothing else.
