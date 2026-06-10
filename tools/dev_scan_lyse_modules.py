from pathlib import Path
import sys
import yaml

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from labpilot_ai.config.settings_manager import SettingsManager
from labpilot_ai.lyse_ctrl.registry_autoscan import merge_autoscanned_lyse_modules


def main():
    settings = SettingsManager()
    project_settings = settings.load_project_settings()
    lyse_registry = settings.load_lyse_registry()

    registry, report = merge_autoscanned_lyse_modules(
        lyse_registry,
        single_dir=project_settings.get("single_modules_dir", ""),
        multi_dir=project_settings.get("multi_modules_dir", ""),
        project_root=settings.project_dir,
        prune_missing=False,
    )

    out = settings.save_lyse_registry(registry)
    print("Saved:", out)
    print(yaml.safe_dump(report, allow_unicode=True, sort_keys=False))


if __name__ == "__main__":
    main()