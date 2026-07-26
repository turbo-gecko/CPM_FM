# Integration Test Coverage Report

**Generated from:** `integration/coverage_manifest.json` v2.1
**Total automated tests:** 61

## Test Tiers

| Tier | Count |
|---|---:|
| hil | 49 |
| visual | 12 |

## Evidence Classification

| Classification | Count |
|---|---:|
| equivalent | 6 |
| partial | 52 |
| supplementary | 3 |
| manual-only | 0 |

## Manual ID Coverage (51 unique IDs)

| MT-ID | Tests | Evidence |
|---|---|---|
| MT-BR02 | 1 | partial |
| MT-BR05 | 1 | partial |
| MT-BR10 | 1 | partial |
| MT-C01 | 1 | partial |
| MT-C05 | 1 | partial |
| MT-C06 | 1 | partial |
| MT-C18 | 1 | partial |
| MT-C19 | 1 | partial |
| MT-CF01 | 1 | partial |
| MT-CF02 | 1 | partial |
| MT-D01 | 1 | partial |
| MT-D05 | 1 | partial |
| MT-F07 | 1 | partial |
| MT-F08 | 1 | partial |
| MT-FV01 | 1 | partial |
| MT-FV02 | 1 | partial |
| MT-G01 | 1 | partial |
| MT-G03 | 1 | partial |
| MT-G05 | 1 | partial |
| MT-G07 | 1 | partial |
| MT-I03 | 1 | partial |
| MT-R01 | 1 | partial |
| MT-R03 | 1 | partial |
| MT-R05 | 1 | partial |
| MT-R08 | 1 | partial |
| MT-R09 | 1 | partial |
| MT-R10 | 1 | partial |
| MT-R11 | 1 | partial |
| MT-S01 | 1 | partial |
| MT-S03 | 1 | partial |
| MT-T03 | 1 | partial |
| MT-T04 | 1 | partial |
| MT-T06 | 1 | partial |
| MT-T07 | 1 | partial |
| MT-T10 | 2 | partial |
| MT-T13 | 1 | partial |
| MT-T15 | 1 | partial |
| MT-T16 | 1 | partial |
| MT-TH01 | 1 | partial |
| MT-V08 | 1 | partial |
| MT-V09 | 1 | partial |
| MT-V12 | 1 | partial |
| MT-W01 | 1 | partial |
| MT-W03 | 1 | partial |
| MT-W05 | 1 | partial |
| MT-W10 | 1 | partial |
| MT-W13 | 2 | partial |
| MT-W17 | 2 | partial |
| MT-W18 | 1 | partial |
| MT-W19 | 1 | partial |
| MT-W20 | 1 | partial |

## Requirements Covered (91 unique)

`DR-033a` `FR-017a` `FR-030` `FR-037` `FR-039` `FR-041` `FR-042` `FR-046` `FR-050` `FR-054` `FR-055` `FR-058` `FR-070` `FR-077` `FR-078` `FR-079` `FR-081` `FR-082` `FR-083` `FR-091` `FR-091a` `FR-094` `FR-095` `FR-096` `FR-097` `FR-099` `FR-100` `FR-101` `FR-102` `FR-105` `FR-106` `FR-107` `FR-108` `FR-111` `FR-114` `FR-117` `FR-118` `FR-120` `FR-125` `FR-137` `FR-138` `FR-140` `FR-142` `FR-145` `FR-146` `FR-147` `FR-148` `FR-149` `FR-150` `FR-151` `FR-152` `FR-153` `FR-153e` `FR-154` `FR-157` `FR-162` `FR-165` `FR-166` `FR-167` `FR-181` `FR-182` `FR-183` `FR-184` `NFR-003b` `NFR-003c` `NFR-003d` `NFR-003e` `NFR-003f` `NFR-003m` `NFR-003q` `NFR-004` `UIR-004` `UIR-014` `UIR-017` `UIR-018` `UIR-019` `UIR-034` `UIR-064` `UIR-069` `UIR-070` `UIR-073` `UIR-076` `UIR-078` `UIR-091` `UIR-099` `UIR-100` `UIR-101` `UIR-102` `UIR-105` `UIR-106` `UIR-107` 

## Test Inventory

| Node ID | Tier | MT-ID | Requirements | Evidence | Gated |
|---|---|---|---|---|---|
| `test_batch_transfer_sequential_multi_file` | hil | MT-T06 | FR-105, FR-106, FR-107 | supplementary | — |
| `test_batch_abort_on_mid_file_failure` | hil | MT-T07 | FR-108 | supplementary | — |
| `test_cancel_upload_while_transferring` | hil | MT-T13 | FR-120, NFR-003m | supplementary | — |
| `test_remote_delete_removes_file` | hil | MT-F08 | FR-111, FR-117, FR-118 | partial | — |
| `test_remote_rename_changes_name` | hil | MT-F07 | FR-111, FR-114, FR-117 | partial | — |
| `test_restore_wipes_scratch_then_uploads` | hil | MT-BR05 | FR-151, FR-152, FR-153, FR-154 | partial | destructive |
| `test_restore_erase_all_sequence_wipes_scratch` | hil | MT-BR10 | FR-153e, UIR-107 | partial | destructive |
| `test_backup_downloads_remote_to_host` | hil | MT-BR02 | FR-150, FR-152, FR-154 | partial | destructive |
| `test_overwrite_existing_remote_file` | hil | MT-CF01 | FR-145, FR-146 | partial | — |
| `test_skip_existing_remote_file` | hil | MT-CF02 | FR-145, FR-147 | partial | — |
| `test_conflict_apply_to_all_persists_across_batch` | hil | — | FR-147 | partial | — |
| `test_connect_opens_ports_and_probes` | hil | MT-C01 | FR-030, FR-037, FR-041, FR-042 | equivalent | — |
| `test_disconnect_closes_ports_and_clears_list` | hil | MT-C05 | FR-050, FR-054, FR-055, FR-058 | equivalent | — |
| `test_reconnect_after_disconnect` | hil | MT-C06 | FR-030, FR-050 | equivalent | — |
| `test_connect_transport_open_failure_reports_error_and_skips_probe` | hil | — | FR-039, FR-046 | partial | two_port |
| `test_rapid_disconnect_during_probe_no_crash` | hil | — | FR-050, NFR-004 | partial | — |
| `test_disconnect_prompt_with_ports_swapped` | hil | MT-C18 | FR-030, FR-050 | partial | two_port |
| `test_load_config_while_connected_closes_ports` | hil | MT-C19 | FR-017a, FR-050 | partial | — |
| `test_internal_drop_host_to_remote_uploads` | hil | MT-D01 | FR-137, FR-138 | partial | — |
| `test_drop_cancelled_does_not_transfer` | hil | MT-D05 | FR-137 | partial | — |
| `test_upload_records_history_entry` | hil | MT-TH01 | FR-140, FR-142 | partial | — |
| `test_invalid_name_rename_uploads_conforming` | hil | MT-FV01 | FR-148, FR-149 | partial | — |
| `test_invalid_name_skip_does_not_upload` | hil | MT-FV02 | FR-148 | partial | — |
| `test_invalid_name_special_chars_sanitized` | hil | — | FR-148, FR-149 | partial | — |
| `test_detect_current_drive` | hil | MT-R03 | DR-033a, FR-041 | partial | — |
| `test_change_to_scratch_drive` | hil | MT-R05 | FR-100, FR-101, FR-102 | partial | — |
| `test_dir_listing_parses` | hil | MT-R01 | FR-077, FR-078, FR-079 | equivalent | — |
| `test_dir_listing_empty_directory` | hil | MT-R08 | FR-077 | partial | — |
| `test_dir_listing_single_file` | hil | MT-R09 | FR-077 | partial | — |
| `test_user_area_switch_lists` | hil | MT-R10 | FR-181, FR-182 | partial | — |
| `test_transfer_targets_selected_user_area` | hil | MT-R11 | FR-183, FR-184 | partial | — |
| `test_round_trip_sample_files` | hil | MT-T03 | FR-081, FR-082, FR-083 | equivalent | — |
| `test_uploaded_file_visible_then_removable` | hil | MT-T04 | FR-099, FR-106, FR-107 | equivalent | — |
| `test_round_trip_1k` | hil | MT-T10 | FR-082, NFR-003b, NFR-003e | partial | — |
| `test_round_trip_checksum` | hil | MT-T10 | FR-082, NFR-003d, NFR-003f | partial | — |
| `test_round_trip_zero_byte_file` | hil | MT-T15 | FR-081, NFR-003q | partial | — |
| `test_round_trip_exactly_128_bytes` | hil | MT-T16 | FR-082, NFR-003c | partial | — |
| `test_round_trip_exactly_1024_bytes` | hil | — | FR-082, NFR-003b | partial | — |
| `test_recv_port_closed_mid_transfer_graceful_failure` | hil | — | FR-082, FR-120 | partial | two_port |
| `test_peer_connects_and_sees_ccp_prompt` | hil | — | FR-041, FR-042 | partial | — |
| `test_terminal_window_shows_live_response` | hil | MT-W01 | FR-091, FR-094, FR-097 | partial | — |
| `test_terminal_window_keyboard_input` | hil | MT-W03 | FR-094, FR-096 | partial | — |
| `test_terminal_window_clear` | hil | MT-W05 | FR-095 | partial | — |
| `test_terminal_context_menu_copy_selection` | hil | MT-W17 | FR-165, UIR-099, UIR-100, UIR-105 | partial | — |
| `test_terminal_context_menu_paste_sends_over_serial` | hil | MT-W17 | FR-094, FR-166 | partial | — |
| `test_terminal_context_menu_reset_size` | hil | MT-W18 | FR-091a, FR-167 | partial | — |
| `test_terminal_context_menu_terminal_type_submenu` | hil | MT-W19 | UIR-034, UIR-101 | partial | — |
| `test_terminal_context_menu_macros_submenu_runs_over_serial` | hil | MT-W20 | FR-162, UIR-102 | partial | — |
| `test_terminal_vt100_escape_sequences_render_without_crash` | hil | MT-W10 | FR-157 | partial | — |
| `test_window_title_contains_app_name` | visual | MT-S01 | FR-125, UIR-078 | partial | — |
| `test_remote_list_empty_at_startup` | visual | MT-S03 | FR-070 | partial | — |
| `test_menubar_has_file_and_help` | visual | MT-G01 | UIR-004 | partial | — |
| `test_drive_combo_lists_a_to_p` | visual | MT-G05 | UIR-017 | partial | — |
| `test_lists_have_context_menus` | visual | MT-G07 | UIR-018, UIR-019 | partial | — |
| `test_main_panes_have_push_buttons` | visual | MT-G03 | UIR-014 | partial | — |
| `test_material_theme_applied` | visual | MT-V08 | UIR-070, UIR-073 | partial | — |
| `test_terminal_window_has_no_control_row_and_font_in_context_menu` | visual | MT-W13 | UIR-064, UIR-069, UIR-106 | partial | — |
| `test_font_dialog_lists_usable_under_material_theme` | visual | MT-W13 | UIR-069 | partial | — |
| `test_about_dialog_contents` | visual | MT-I03 | UIR-076 | partial | — |
| `test_manual_dialog_renders` | visual | MT-V09 | UIR-091 | partial | — |
| `test_i18n_language_switch_updates_ui` | visual | MT-V12 | UIR-076 | partial | — |

## Notes

- Tests marked `partial` exercise a meaningful subset but leave some manual evidence unverified.
- Tests marked `supplementary` verify related internal logic but do not perform the manual workflow.
- Destructive tests require `--run-destructive` and a configured scratch drive.
- Two-port gated tests require a target with distinct Terminal/Transport ports.
