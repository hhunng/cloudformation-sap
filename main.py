import json
import yaml

def lambda_handler(event, context):
    template = event['fragment']
    parameters = template.get('Parameters', {})
    resources = template.get('Resources', {})
    
    # Parse configuration from parameters
    config_data = {}
    for param_name, param_value in parameters.items():
        if param_name.endswith('Config'):
            config_data.update(yaml.safe_load(param_value['Default']))
    
    # Generate replicated resources
    new_resources = {}
    resource_mappings = {}  # Track generated resource names for references
    
    for resource_name, resource_def in resources.items():
        resource_type = resource_def.get('Type')
        properties = resource_def.get('Properties', {})
        
        # Only replicate resources that have config references
        if not has_config_references(properties):
            new_resources[resource_name] = resource_def
            continue
            
        # Find which config array this resource should replicate from
        config_key = find_config_key(properties, config_data)
        
        if config_key and config_key in config_data:
            # Generate multiple resources based on config array
            for i, config_item in enumerate(config_data[config_key]):
                new_resource_name = f"{resource_name}{i+1}"
                new_resource = {
                    'Type': resource_type,
                    'Properties': process_properties(properties, config_item, resource_mappings)
                }
                
                # Copy other attributes
                for attr in ['UpdateReplacePolicy', 'DeletionPolicy', 'DependsOn', 'Condition']:
                    if attr in resource_def:
                        new_resource[attr] = resource_def[attr]
                
                new_resources[new_resource_name] = new_resource
                
                # Track mapping for references
                if config_key not in resource_mappings:
                    resource_mappings[config_key] = {}
                resource_mappings[config_key][config_item.get('name', f"item{i+1}")] = new_resource_name
        else:
            # Keep non-replicated resources as-is
            new_resources[resource_name] = resource_def
    
    # Update template
    template['Resources'] = new_resources
    
    return {
        'requestId': event['requestId'],
        'status': 'success',
        'fragment': template
    }

def find_config_key(properties, config_data):
    """Find which config array this resource should use based on property patterns"""
    def check_value(value):
        if isinstance(value, str) and '.' in value:
            config_key = value.split('.')[0]
            if config_key in config_data:
                return config_key
        elif isinstance(value, list):
            for item in value:
                result = check_value(item)
                if result:
                    return result
        elif isinstance(value, dict):
            for v in value.values():
                result = check_value(v)
                if result:
                    return result
        return None
    
    for prop_value in properties.values():
        result = check_value(prop_value)
        if result:
            return result
    return None

def has_config_references(properties):
    """Check if resource has any config pattern references (config_key.attribute)"""
    def check_value(value):
        if isinstance(value, str) and '.' in value and not value.startswith('!'):
            return True
        elif isinstance(value, list):
            return any(check_value(item) for item in value)
        elif isinstance(value, dict):
            return any(check_value(v) for v in value.values())
        return False
    
    return any(check_value(prop_value) for prop_value in properties.values())

def process_properties(properties, config_item, resource_mappings):
    """Process properties, replacing placeholders with actual values and resolving references"""
    processed = {}
    
    for key, value in properties.items():
        processed[key] = process_value(value, config_item, resource_mappings)
    
    return processed

def process_value(value, config_item, resource_mappings):
    """Recursively process values, handling strings, lists, and dicts"""
    if isinstance(value, str):
        return process_string_value(value, config_item, resource_mappings)
    elif isinstance(value, list):
        return [process_value(item, config_item, resource_mappings) for item in value]
    elif isinstance(value, dict):
        return {k: process_value(v, config_item, resource_mappings) for k, v in value.items()}
    else:
        return value

def process_string_value(value, config_item, resource_mappings):
    """Process string values, replacing config references and resource references"""
    if '.' in value:
        parts = value.split('.')
        if len(parts) == 2:
            config_key, attr = parts
            
            # Handle resource references (e.g., "subnets.vpcIdRef")
            if attr.endswith('Ref') and config_key in resource_mappings:
                ref_name = config_item.get(attr)
                if ref_name:
                    # Find the actual resource name from mappings
                    for resource_type, mappings in resource_mappings.items():
                        if ref_name in mappings:
                            return {'Ref': mappings[ref_name]}
                    # If not found in mappings, try direct reference
                    return {'Ref': ref_name}
            
            # Handle direct config value references (e.g., "vpcs.cidr")
            elif attr in config_item:
                return config_item[attr]
    
    return value
