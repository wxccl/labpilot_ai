# Package Templates

The PyPI package includes clean starter templates. They are copied into the current project directory on first run or when the user clicks `Init/repair project templates`.

Included package data:

- `labpilot_ai/label.png`
- `labpilot_ai/templates/configs/*.yaml`
- `labpilot_ai/templates/manual/**/*.md`
- `labpilot_ai/templates/plugins/single_modules/*.py`
- `labpilot_ai/templates/plugins/multi_modules/*.py`

Local user-editable copies:

- `configs/`
- `manual/`
- `plugins/`

Example:

```python
from labpilot_ai.config.settings_manager import SettingsManager

settings = SettingsManager()
settings.ensure_project_templates(include_manual=True)
```

Existing local files are not overwritten. Registry saves create `.bak` backups before replacing YAML files.

Recommended workflow:

1. Install or update LabPilot AI.
2. Start the UI.
3. Open Settings or Directory.
4. Click `Init/repair project templates`.
5. Edit only the local `configs/`, `manual/`, and `plugins/` copies for the current lab project.

This keeps the installed package clean while allowing every experiment folder to keep its own paths, registry entries, plugins, and notes.
