# Integration Test Coverage Report

**Generated from:** `integration/coverage_manifest.json` v3.0
**Total collected test functions:** 70
**Execution status:** Not run by this generator; physical outcomes remain in `integration/results/runs_ledger.json`.

## Test Tiers

| Tier | Count |
|---|---:|
| gui-integration | 3 |
| hil | 55 |
| visual | 12 |

## Evidence Classification

| Classification | Count |
|---|---:|
| equivalent | 0 |
| partial | 53 |
| supplementary | 17 |
| manual-only | 0 |

## Manual Scenario Decisions

- Manual plan cases: **217**
- Cases with reviewed automated support: **47** (**21.7%** raw mapped-case ratio)
- Every remaining case has an explicit `manual-only` decision in the manifest.

| MT-ID | Tests | Best evidence | Manual retained |
|---|---:|---|---|
| MT-BR03 | 1 | partial | yes |
| MT-BR05 | 1 | partial | yes |
| MT-BR10 | 1 | partial | yes |
| MT-C01 | 1 | partial | yes |
| MT-C02 | 1 | partial | yes |
| MT-C03 | 1 | partial | yes |
| MT-C04 | 1 | partial | yes |
| MT-C09 | 1 | partial | yes |
| MT-C18 | 1 | partial | yes |
| MT-C19 | 1 | partial | yes |
| MT-CF04 | 2 | partial | yes |
| MT-CF05 | 1 | partial | yes |
| MT-D03 | 1 | partial | yes |
| MT-D06 | 1 | partial | yes |
| MT-DI04 | 1 | partial | yes |
| MT-DI14 | 1 | partial | yes |
| MT-DI21 | 1 | partial | yes |
| MT-F01 | 1 | partial | yes |
| MT-F06 | 2 | partial | yes |
| MT-FV02 | 1 | partial | yes |
| MT-FV04 | 1 | partial | yes |
| MT-I02 | 1 | partial | yes |
| MT-R01 | 1 | partial | yes |
| MT-R04 | 1 | partial | yes |
| MT-R05 | 1 | partial | yes |
| MT-R10 | 1 | partial | yes |
| MT-R11 | 1 | partial | yes |
| MT-S02 | 1 | partial | yes |
| MT-S03 | 1 | partial | yes |
| MT-S05 | 2 | partial | yes |
| MT-T03 | 1 | partial | yes |
| MT-T06 | 1 | partial | yes |
| MT-T07 | 1 | partial | yes |
| MT-T08 | 1 | partial | yes |
| MT-T10 | 2 | partial | yes |
| MT-T11 | 1 | partial | yes |
| MT-T13 | 1 | partial | yes |
| MT-V01 | 1 | partial | yes |
| MT-V10 | 1 | partial | yes |
| MT-W01 | 1 | partial | yes |
| MT-W03 | 1 | partial | yes |
| MT-W06 | 1 | partial | yes |
| MT-W13 | 2 | partial | yes |
| MT-W17 | 2 | partial | yes |
| MT-W18 | 1 | partial | yes |
| MT-W19 | 1 | partial | yes |
| MT-W20 | 1 | partial | yes |

## Test Inventory

| Test | Tier | MT-ID | Requirements | Evidence | Gated |
|---|---|---|---|---|---|
| `test_batch_abort_on_mid_file_failure` | hil | MT-T07 | FR-108 | partial | — |
| `test_batch_transfer_sequential_multi_file` | hil | MT-T06 | FR-105, FR-106, FR-107 | partial | — |
| `test_cancel_during_later_batch_file` | hil | — | FR-120 | supplementary | — |
| `test_cancel_upload_while_transferring` | hil | MT-T13 | FR-120, NFR-003m | partial | — |
| `test_remote_delete_removes_file` | hil | MT-F06 | FR-111, FR-117, FR-118 | partial | — |
| `test_remote_rename_changes_name` | hil | MT-F06 | FR-111, FR-114, FR-117 | partial | — |
| `test_backup_downloads_remote_to_host` | hil | MT-BR03 | FR-150, FR-153, FR-154 | partial | destructive |
| `test_restore_erase_all_sequence_wipes_scratch` | hil | MT-BR10 | FR-153e, UIR-107 | partial | destructive |
| `test_restore_wipes_scratch_then_uploads` | hil | MT-BR05 | FR-151, FR-152, FR-153, FR-154 | partial | destructive |
| `test_conflict_apply_to_all_persists_across_batch` | hil | MT-CF05 | FR-147 | partial | — |
| `test_overwrite_existing_remote_file` | hil | MT-CF04 | FR-145, FR-146 | partial | — |
| `test_skip_existing_remote_file` | hil | MT-CF04 | FR-145, FR-147 | partial | — |
| `test_connect_opens_ports_and_probes` | hil | MT-C01 | FR-030, FR-037, FR-041, FR-042 | partial | — |
| `test_disconnect_closes_ports_and_clears_list` | hil | MT-C09 | FR-050, FR-054, FR-055, FR-058 | partial | — |
| `test_disconnect_prompt_with_ports_swapped` | hil | MT-C18 | FR-030, FR-050 | partial | two_port |
| `test_load_config_while_connected_closes_ports` | hil | MT-C19 | FR-017a, FR-050 | partial | — |
| `test_rapid_disconnect_during_probe_no_crash` | hil | — | FR-050, NFR-004 | supplementary | — |
| `test_reconnect_after_disconnect` | hil | — | FR-030, FR-050 | supplementary | — |
| `test_bad_terminal_port_reports_error_and_stays_disconnected` | gui-integration | MT-C02 | FR-031, FR-033 | partial | — |
| `test_bad_transport_port_reports_error_and_skips_probe` | gui-integration | MT-C04 | FR-039, FR-046 | partial | — |
| `test_distinct_terminal_and_transport_ports_connect_both` | gui-integration | MT-C03 | FR-038, FR-040, UIR-074 | partial | — |
| `test_disk_image_host_mount_copy_to_remote` | hil | MT-DI04 | FR-106, FR-145, FR-171 | partial | — |
| `test_disk_image_user_area_transfer_preserves_source` | hil | MT-DI21 | FR-188 | partial | — |
| `test_remote_image_mount_refuses_connect` | hil | MT-DI14 | FR-176 | partial | — |
| `test_drop_cancelled_does_not_transfer` | hil | MT-D06 | FR-137 | partial | — |
| `test_internal_drop_host_to_remote_uploads` | hil | MT-D03 | FR-137, FR-138 | partial | — |
| `test_upload_records_history_entry` | hil | — | FR-140, FR-142 | supplementary | — |
| `test_invalid_name_rename_uploads_conforming` | hil | MT-FV02 | FR-148, FR-149 | partial | — |
| `test_invalid_name_skip_does_not_upload` | hil | MT-FV04 | FR-149 | partial | — |
| `test_invalid_name_special_chars_sanitized` | hil | — | FR-148, FR-149 | supplementary | — |
| `test_inter_file_wait_and_post_final_settle` | hil | MT-T08 | FR-109 | partial | — |
| `test_inter_file_wait_terminal_shows_prompt_between_files` | hil | — | FR-109 | supplementary | — |
| `test_change_to_scratch_drive` | hil | MT-R05 | FR-100, FR-101, FR-102 | partial | — |
| `test_detect_current_drive` | hil | — | DR-033a, FR-041 | supplementary | — |
| `test_dir_listing_empty_directory` | hil | — | FR-077 | supplementary | destructive |
| `test_dir_listing_parses` | hil | MT-R01 | FR-077, FR-078, FR-079 | partial | — |
| `test_dir_listing_single_file` | hil | MT-R04 | FR-077 | partial | destructive |
| `test_transfer_targets_selected_user_area` | hil | MT-R11 | FR-183, FR-184 | partial | — |
| `test_user_area_switch_lists` | hil | MT-R10 | FR-181, FR-182 | partial | — |
| `test_recv_port_closed_mid_transfer_graceful_failure` | hil | — | FR-082, FR-120 | supplementary | two_port |
| `test_round_trip_1k` | hil | MT-T10 | FR-082, NFR-003b, NFR-003e | partial | — |
| `test_round_trip_checksum` | hil | MT-T10 | FR-082, NFR-003d, NFR-003f | partial | — |
| `test_round_trip_exactly_1024_bytes` | hil | — | FR-082, NFR-003b | supplementary | — |
| `test_round_trip_exactly_128_bytes` | hil | — | FR-082, NFR-003c | supplementary | — |
| `test_round_trip_sample_files` | hil | MT-T03 | FR-081, FR-082, FR-083 | partial | — |
| `test_round_trip_zero_byte_file` | hil | — | FR-081, NFR-003q | supplementary | — |
| `test_uploaded_file_visible_then_removable` | hil | — | FR-099, FR-106, FR-107 | supplementary | — |
| `test_peer_connects_and_sees_ccp_prompt` | hil | — | FR-041, FR-042 | supplementary | — |
| `test_terminal_context_menu_copy_selection` | hil | MT-W17 | FR-165, UIR-099, UIR-100, UIR-105 | partial | — |
| `test_terminal_context_menu_macros_submenu_runs_over_serial` | hil | MT-W20 | FR-162, UIR-102 | partial | — |
| `test_terminal_context_menu_paste_sends_over_serial` | hil | MT-W17 | FR-094, FR-166 | partial | — |
| `test_terminal_context_menu_reset_size` | hil | MT-W18 | FR-091a, FR-167 | partial | — |
| `test_terminal_context_menu_terminal_type_submenu` | hil | MT-W19 | UIR-034, UIR-101 | partial | — |
| `test_terminal_vt100_escape_sequences_render_without_crash` | hil | — | FR-157 | supplementary | — |
| `test_terminal_window_clear` | hil | MT-W06 | FR-095 | partial | — |
| `test_terminal_window_keyboard_input` | hil | MT-W03 | FR-094, FR-096 | partial | — |
| `test_terminal_window_shows_live_response` | hil | MT-W01 | FR-091, FR-094, FR-097 | partial | — |
| `test_ui_responsive_during_large_transfer` | hil | MT-T11 | NFR-001 | partial | — |
| `test_about_dialog_contents` | visual | MT-V10 | UIR-076 | partial | — |
| `test_drive_combo_lists_a_to_p` | visual | MT-S05 | UIR-017 | partial | — |
| `test_font_dialog_lists_usable_under_material_theme` | visual | MT-W13 | UIR-069, UIR-070 | partial | — |
| `test_language_menu_switch_retranslates_ui` | visual | MT-I02 | FR-123 | partial | — |
| `test_lists_have_context_menus` | visual | MT-F01 | UIR-018, UIR-019 | partial | — |
| `test_main_panes_have_push_buttons` | visual | MT-S05 | UIR-014 | partial | — |
| `test_manual_dialog_renders` | visual | — | UIR-091 | supplementary | — |
| `test_material_theme_applied` | visual | MT-V01 | UIR-070, UIR-073 | partial | — |
| `test_menubar_has_file_and_help` | visual | MT-S03 | UIR-004 | partial | — |
| `test_remote_list_empty_at_startup` | visual | MT-S02 | FR-070 | partial | — |
| `test_terminal_window_has_no_control_row_and_font_in_context_menu` | visual | MT-W13 | UIR-064, UIR-069, UIR-106 | partial | — |
| `test_window_title_contains_app_name` | visual | — | FR-125 | supplementary | — |

## Interpretation

- `partial` means the exact manual scenario has reviewed automated support, but retained steps or evidence remain.
- `supplementary` means requirement evidence only; it does not count as a mapped manual scenario.
- No test is currently labelled `equivalent`.
- Pass, Fail, Blocked, Skipped, and N-A are execution outcomes and are not inferred from collection.
