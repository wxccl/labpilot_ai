# Keep managed data under the active Runmanager output

Set `host.runmanager.batch_root` to the literal string `@runmanager_output` and set `host.runmanager.output_root` to the approved data root. The reviewed Runmanager snapshot must select an **existing absolute local directory** beneath that root (or the root itself). A missing, out-of-policy or UNC destination is refused; unchanged fixed-directory batch_root profiles continue working. This does not switch a production UNC path automatically.

For an approved submission each H5 is created in a new request-ID subdirectory of the selected folder. The Runmanager UI output selection is restored before queue submission. This is not flat native output naming. BLACS callbacks must match both the journal's exact directory and generated shot identity. Do not change the profile or move the files during observation. Recheck discovery, perform one supervised test and inspect the manifest before treating a new storage setup as validated.
