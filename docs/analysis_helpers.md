# Importing station helpers in a Lyse routine

In the profile's existing `analysis` object, add an optional `"sys_path": ["analysis_helpers"]`. Relative entries resolve against the profile directory; absolute directories are supported. Use narrow, operator-controlled directories. The isolated Python worker appends them after standard and installed packages for the duration of the trusted routine; no bridge routine or global PYTHONPATH change is required. Existing profiles need no change.

The ordered directory list participates in the analysis configuration digest. The main Python routine is hash-pinned, but helper contents are not: version, review and protect helper code before use, and create a new reviewed profile when changing it. Stage profile changes before starting an experiment. This option configures the independent analysis worker; it does not register an analysis routine in a running Lyse GUI.
