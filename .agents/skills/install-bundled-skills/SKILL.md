---
name: install-bundled-skills
description: Bundle agent skills with a Python package, install them in a repository, and check installed copies.
---

This skill is bundled with the `coloph-install-skills` package.

When reading this skill, please do not confuse three packagges and codebases:

- `coloph-install-skills` which you have installed
- package that you are developing (let's call it `yak-shaving-example-package`)
- codebase `yak-shaving-example-package` get installed into

## Build your skills

Put each skill in the `bundled_agent_skills` directory of the Python import package:

```text
src/yak_shaving_example_package/bundled_agent_skills/shaving-yaks-example-skill/
├── SKILL.md
├── references/
├── scripts/
└── assets/
```

Add `coloph-install-skills` to the package dependencies:

```sh
uv add coloph-install-skills
```

It is recommended to put this line on the top of every `SKILL.md` file:

```text
This skill is bundled with the `yak-shaving-example-package` package.
```

## Recommendations on skill design

Skills are documentation for agents, not humans. The main advantage of skills is that their descriptions are automatically injected into context by agent's harness, so it's easier for them to remember and use them.

Look at your package's README file. This is something that agents read when they install the package, so detailed descriptions and installation instructions belong there. But agents do not remember to read it again when they maintain something related to your package. That's what you should move to skills.

Do not create too many skills. Most packages need one or two.  Give each skill a goal-oriented name and description. Make the situations that require the skill obvious.  Consider the files, systems, tasks, and keywords that occur in those situations. Use them to make automatic discovery reliable.  Keep internal implementation details out of the description. Put necessary details in the skill body or supporting references.

Many agent hosts provide a skill-authoring tool, such as `/create-skill`. Use one when it is available.

## Check your skills

Run this command in continuous integration to detect missing, changed, or broken installations:

```sh
uv run coloph-install-skills --check
```

Add `--root PATH` when the repository is not the current directory.

## Include your skills in your package's installation

In your package install documentation, instruct users to run `coloph-install-skills` command after installing your package. For example, put this in your README.md:

```markdown
To install this package, run `uv run yak-shaving-example-package`, and then `uv run coloph-install-skills` to install bundled agent skills. Add this line to your AGENTS.md file:

> After installing dependencies, run `uv run coloph-install-skills` to install or update skills bundled with installed packages.
```

The command copies each complete skill to `.agents/skills/`. It creates a relative link in `.claude/skills/`.
The command updates skills that it installed before. It does not overwrite other files.
When several packages depend on `coloph-install-skills`, the skills of all packages will be installed/updated when this commadn is ran.
