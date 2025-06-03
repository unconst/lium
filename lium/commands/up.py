"""Rent pods command for Lium CLI."""

import click
import re
import json
import requests
from typing import Optional, Dict, List, Any, Tuple

from ..config import get_or_set_api_key, get_or_set_ssh_key, get_config_value
from ..api import LiumAPIClient
from ..styles import styled
from ..helpers import *


def select_template_interactively(client: LiumAPIClient, skip_prompts: bool = False) -> Optional[str]:
    """Fetches templates. If skip_prompts, uses first. Else, asks to use first, then lists all if user says no."""
    try:
        templates = client.get_templates()
        if not templates: console.print(styled("No templates found.", "warning")); return None

        first_template = templates[0]
        first_template_id = first_template.get("id")
        tpl_name = first_template.get("name", "Unnamed Template")
        tpl_image = first_template.get("docker_image", "N/A")
        tpl_tag = first_template.get("docker_image_tag", "latest")
        # Full description for default prompt
        default_desc_full = f"'{tpl_name}' ({tpl_image}:{tpl_tag}, ID: ...{first_template_id[-8:] if first_template_id else 'N/A'})"
        default_desc_for_confirmation = f"'{tpl_name}' ({tpl_image}:{tpl_tag}) ID: {first_template_id}" # For --yes message

        if skip_prompts:
            if first_template_id:
                console.print(styled(f"Using default template: {default_desc_for_confirmation}", "info"))
                return first_template_id
            else:
                console.print(styled("Error: Default first template has no ID. Cannot proceed with --yes.", "error"))
                return None
        else: 
            console.print("\n" + styled(f"Default template: {default_desc_full}", "info"))
            if Prompt.ask(styled("Use this template?", "key"), default="y", console=console).lower().startswith("y"):
                if first_template_id: 
                    # console.print(styled(f"Selected default template: {default_desc_for_confirmation}", "info")) # Optional: confirm selection
                    return first_template_id
                else: console.print(styled("Error: Default template invalid. Select from list.", "error"))
            
            console.print(styled("Fetching all available templates...", "info"))
            table = Table(title=styled("Available Templates", "title"), box=None, show_header=True, show_lines=False, show_edge=False, padding=(0, 1), header_style="table.header", title_style="title", expand=True)
            table.add_column("#", style="dim", justify="right")
            table.add_column("Name", style="primary", min_width=20, max_width=30, overflow="ellipsis")
            table.add_column("Docker Image", style="info", min_width=30, max_width=45, overflow="ellipsis")
            table.add_column("Category", style="secondary", width=10)
            table.add_column("ID", style="muted", width=15, overflow="ellipsis")
            template_map = {}
            for idx, tpl in enumerate(templates, 1):
                template_map[str(idx)] = tpl.get("id")
                docker_image_full = f"{tpl.get('docker_image', 'N/A')}:{tpl.get('docker_image_tag', 'latest')}"
                table.add_row(str(idx), tpl.get("name", "N/A"), docker_image_full, tpl.get("category", "N/A"), tpl.get("id", "N/A")[:13] + "..." if tpl.get("id") else "N/A")
            console.print(table)
            console.print(styled("Enter # or full ID of template to use:", "key"))
            choice = Prompt.ask("", console=console, show_default=False).strip()
            if choice in template_map: 
                # selected_tpl_name = next((t['name'] for t in templates if t['id'] == template_map[choice]), "Selected Template")
                # console.print(styled(f"Selected template: '{selected_tpl_name}' (ID: {template_map[choice]})", "info")) # Optional
                return template_map[choice]
            elif any(tpl['id'] == choice for tpl in templates): 
                # selected_tpl_name = next((t['name'] for t in templates if t['id'] == choice), "Selected Template")
                # console.print(styled(f"Selected template: '{selected_tpl_name}' (ID: {choice})", "info")) # Optional
                return choice
            else: console.print(styled("Invalid selection.", "error")); return None
    except requests.exceptions.RequestException as e: console.print(styled(f"API Error fetching templates: {str(e)}", "error")); return None
    except Exception as e: console.print(styled(f"Error processing templates: {str(e)}", "error")); return None


@click.command(name="up", help="Rent pod(s) on executor(s) specified by Name (Executor HUID/UUID).")
@click.argument("executor_names_or_ids", type=str, nargs=-1)
@click.option("--prefix", "pod_name_prefix_opt", type=str, required=False, help="Prefix for pod names. If single executor, this is the exact pod name.")
@click.option("--image", "template_id_option", type=str, required=False, help="The UUID of the template to use (optional).")
@click.option("-y", "--yes", "skip_all_prompts", is_flag=True, help="Skip all confirmations. Uses configured/default template if --template-id is not set.")
@click.option("--api-key", envvar="LIUM_API_KEY", help="API key for authentication")
def up_command(
    executor_names_or_ids: Tuple[str, ...],
    template_id_option: Optional[str],
    skip_all_prompts: bool,
    api_key: Optional[str],
    pod_name_prefix_opt: Optional[str]
):
    if not api_key: api_key = get_or_set_api_key()
    if not api_key: console.print(styled("Error: No API key found.", "error")); return
    ssh_public_keys = get_or_set_ssh_key()
    if not ssh_public_keys: console.print(styled("Error: No SSH public keys found.", "error")); return
    
    if executor_names_or_ids == None or len(executor_names_or_ids) == 0:
        console.print( styled('\nUse: `lium ls <GPU>` for get a pod name. (i.e. lium up 4090)\n', 'info'))
        return
    
    client = LiumAPIClient(api_key)
    template_id_to_use: Optional[str] = None
    template_name_for_display: str = "Unknown Template"
    template_source_info: str = ""

    if template_id_option:
        template_id_to_use = template_id_option
        # Fetch name for display if possible
        try: 
            templates = client.get_templates() # Potentially cache this if called multiple times
            found = next((t for t in templates if t.get("id") == template_id_to_use), None)
            if found: template_name_for_display = found.get("name", template_id_to_use)
            else: template_name_for_display = template_id_to_use + " (not found in list)"
        except: template_name_for_display = template_id_to_use + " (details unavailable)"
        template_source_info = styled(f"Using provided template: '{template_name_for_display}' (ID: ...{template_id_to_use[-12:]})", "info")
    else:
        configured_default_id = get_config_value("template.default_id")
        if configured_default_id:
            template_id_to_use = configured_default_id
            try: 
                templates = client.get_templates()
                found = next((t for t in templates if t.get("id") == template_id_to_use), None)
                if found: template_name_for_display = found.get("name", template_id_to_use)
                else: template_name_for_display = template_id_to_use + " (not found in list)"
            except: template_name_for_display = template_id_to_use + " (details unavailable)"
            if skip_all_prompts:
                template_source_info = styled(f"Using default template from config: '{template_name_for_display}' (ID: ...{template_id_to_use[-12:]})", "info")
            # If not skipping prompts, template_name_for_display is set, actual confirmation comes later
        else: # No option, no config default -> interactive or API default
            # select_template_interactively now only called if truly no prior template source
            # it also handles its own skip_prompts logic for API default.
            selected_template_id_interactive = select_template_interactively(client, skip_prompts=skip_all_prompts)
            if not selected_template_id_interactive:
                # Error/abort messages handled within select_template_interactively
                return
            template_id_to_use = selected_template_id_interactive
            try: # Get name for display from interactive selection
                templates = client.get_templates() # Potentially re-fetch or use cached
                found = next((t for t in templates if t.get("id") == template_id_to_use), None)
                if found: template_name_for_display = found.get("name", template_id_to_use)
                else: template_name_for_display = template_id_to_use
            except: template_name_for_display = template_id_to_use
            # For interactive path, message about template used is part of the final confirmation or handled by select_template_interactively if --yes
            if skip_all_prompts: # If --yes led to API default, select_template_interactively printed it
                 pass # message already printed
            else: # Template was interactively selected
                 template_source_info = styled(f"Using selected template: '{template_name_for_display}' (ID: ...{template_id_to_use[-12:]})", "info")
    
    if not template_id_to_use:
        console.print(styled("Error: No template specified or selected.", "error"))
        return
    
    if template_source_info: # Print template source only if it wasn't part of an interactive prompt already
        console.print(template_source_info)

    # Fetch full template details for display in the final confirmation prompt
    full_template_display_name = template_id_to_use # Fallback to ID
    if template_id_to_use:
        try:
            # This might re-fetch if select_template_interactively was just called,
            # consider passing template details down or caching if performance becomes an issue.
            templates_list_for_name = client.get_templates() 
            found_template_details = next((tpl for tpl in templates_list_for_name if tpl.get("id") == template_id_to_use), None)
            if found_template_details:
                tpl_name = found_template_details.get("name", "Unnamed")
                tpl_image = found_template_details.get("docker_image", "N/A")
                tpl_tag = found_template_details.get("docker_image_tag", "latest")
                full_template_display_name = f"'{tpl_name}' ({tpl_image}:{tpl_tag})"
            else:
                full_template_display_name = f"ID '{template_id_to_use}' (details not found)"
        except Exception as e:
            # console.print(styled(f"Warning: Could not fetch full details for template {template_id_to_use}: {e}", "dim"))
            full_template_display_name = f"ID '{template_id_to_use}' (fetch error)"

    # ... (HUID resolution logic - largely unchanged, ensure `all_executors_data` is fetched once if needed)
    raw_identifiers = []
    for item in executor_names_or_ids: raw_identifiers.extend(item.strip() for item in item.split(',') if item.strip())
    target_identifiers = [ident for ident in raw_identifiers if ident]
    if not target_identifiers: console.print(styled("Error: No executor Names (HUIDs) or UUIDs provided.", "error")); return
    executors_to_process: List[Dict[str, Any]] = []; all_executors_data = None; failed_resolutions = []
    # Fetch executor list once if any HUIDs are present or if we need to resolve UUIDs to HUIDs for API pod_name
    fetch_all_execs = any(bool(re.match(r"^[a-z]+-[a-z]+-[0-9a-f]{2}$", ident.lower())) or '-' in ident for ident in target_identifiers)
    if fetch_all_execs:
        try: all_executors_data = client.get_executors()
        except Exception as e: console.print(styled(f"Critical Error: Could not fetch executor list: {str(e)}", "error")); return

    for i, identifier in enumerate(target_identifiers):
        executor_id_to_rent = None; pod_name_for_api_base = identifier # Base for API pod_name if no prefix
        is_likely_huid = bool(re.match(r"^[a-z]+-[a-z]+-[0-9a-f]{2}$", identifier.lower()))
        if is_likely_huid:
            if not all_executors_data: failed_resolutions.append(identifier + " (no executor data)"); continue
            found_executor = False
            for executor in all_executors_data:
                ex_id = executor.get("id", ""); current_huid = generate_human_id(ex_id)
                if current_huid == identifier.lower(): executor_id_to_rent = ex_id; pod_name_for_api_base = current_huid; found_executor = True; break
            if not found_executor: failed_resolutions.append(identifier); continue
        else: # Assume UUID
            executor_id_to_rent = identifier 
            found_huid_for_uuid = False
            if all_executors_data:
                for executor in all_executors_data:
                    if executor.get("id", "") == identifier: pod_name_for_api_base = generate_human_id(identifier); found_huid_for_uuid = True; break
            # If UUID not found in all_executors_data to get its HUID, pod_name_for_api_base remains the UUID
            if not found_huid_for_uuid: pod_name_for_api_base = identifier 
        if not executor_id_to_rent: failed_resolutions.append(identifier + " (ID error)"); continue
        
        final_instance_name_for_api = pod_name_prefix_opt
        if len(target_identifiers) > 1: final_instance_name_for_api = f"{pod_name_prefix_opt or pod_name_for_api_base}-{i+1}"
        elif pod_name_prefix_opt: final_instance_name_for_api = pod_name_prefix_opt
        else: final_instance_name_for_api = pod_name_for_api_base
        executors_to_process.append({"executor_id": executor_id_to_rent, "pod_name_for_api": final_instance_name_for_api, "original_ref": identifier})
    
    if failed_resolutions: console.print(styled(f"Warning: Unresolved: {', '.join(failed_resolutions)}", "warning"))
    if not executors_to_process: console.print(styled("No valid executors to process.", "info")); return
    
    console.print("\n" + styled("Pods to be acquired:", "header"))
    for proc_info in executors_to_process: console.print(styled(f"  - {proc_info['original_ref']}", "info"))
    console.print("")

    if not skip_all_prompts:
        # Use full_template_display_name in the confirmation prompt
        console.print(styled(f"Template: {full_template_display_name}", "info"))
        confirm_msg = f"Acquire {len(executors_to_process)} pod(s)?"
        if not Prompt.ask(styled(confirm_msg, "key"), default="n", console=console).lower().startswith("y"):
            console.print(styled("Operation cancelled.", "info")); return
    
    # ... (renting loop and final summary) ...
    success_count = 0; failure_count = 0; failed_details = []
    for proc_info in executors_to_process:
        executor_id, pod_name_for_api, original_ref = proc_info['executor_id'], proc_info['pod_name_for_api'], proc_info['original_ref']
        try:
            client.rent_pod(executor_id=executor_id, pod_name=pod_name_for_api, template_id=template_id_to_use, user_public_keys=ssh_public_keys)
            success_count += 1
        except requests.exceptions.HTTPError as e:
            error_message = f"API Error {e.response.status_code}"; failure_count += 1
            try: error_details = e.response.json(); detail_msg = error_details.get('detail'); error_message += f" - {detail_msg if isinstance(detail_msg, str) else json.dumps(detail_msg)}" 
            except json.JSONDecodeError: error_message += f" - {e.response.text[:70]}"
            failed_details.append(f"'{original_ref}' (as '{pod_name_for_api}'): {error_message}")
        except Exception as e: 
            failed_details.append(f"'{original_ref}' (as '{pod_name_for_api}'): Unexpected error: {str(e)[:70]}"); failure_count += 1
  
    if success_count > 0: console.print(styled(f"Successfully acquired {success_count} pod(s).", "success"))
    if failure_count > 0: 
        console.print(styled(f"Failed to acquire {failure_count} pod(s):", "error"))
        for detail in failed_details:
            console.print(styled(f"  - {detail}", "error"))
    if success_count > 0: 
        console.print(styled("Note: Use 'lium ps' to check pod status.", "info"))
        console.print(styled(f"Note: Use 'lium config set tempalte.default_id' to change the default template", "info"))
    elif not executors_to_process and not failed_resolutions : console.print(styled("No action taken.", "info")) 