#!/usr/bin/env python3
"""
Generate a YAML file with all permutations of API keys and model names.
"""

import yaml
import itertools
from typing import List

def generate_permutations(api_key_list: List[str], model_name_list: List[str]) -> List[dict]:
    """
    Generate all permutations of API keys and model names.

    Args:
        api_key_list: List of API keys
        model_name_list: List of model names

    Returns:
        List of dictionaries in the required format
    """
    # Create all combinations of model_name and api_key
    combinations = list(itertools.product(model_name_list, api_key_list))

    # Format into the required structure
    result = []
    for model_name, api_key in combinations:
        result.append({
            'model_name': model_name,
            'litellm_params': {
                'model': f'openai/{model_name}',
                'api_base': 'https://api.siliconflow.cn/v1/',
                'api_key': api_key
            }
        })

    return result

def write_yaml_file(data: List[dict], filename: str = 'config.yaml'):
    """
    Write the data to a YAML file.

    Args:
        data: List of dictionaries to write
        filename: Name of the output YAML file
    """
    yaml_data = {'model_list': data}

    with open(filename, 'w') as f:
        yaml.dump(yaml_data, f, default_flow_style=False, allow_unicode=True)

    print(f"YAML file '{filename}' has been generated successfully.")

def main():
    # Define your API keys and model names here
    api_key_list = [
        "sk-lpmyvqctuwefjzvhgmqdshokdwymtbwbzignobarltucaiwe",
        "sk-joozoveuwkojwjhlmwlqlkjxpkjneqzdhscslogdeykrzehv",
        "sk-oonrlsjwpzuhkpwifmbkignkexlsiyqhzwdyhixxnuzwosoh",
        "sk-zvmriplwnxlkdsohfllisazvebfbeztqpbimijowyyegedyo"
    ]

    model_name_list = [
        "claude-3-5-sonnet-20241022",
        "Qwen/Qwen3-Coder-30B-A3B-Instruct",
        "Qwen/Qwen3-Coder-30B-A3B-Thinking",
        "Qwen/Qwen3-Coder-480B-A35B-Instruct",
        "Qwen/Qwen3-VL-235B-A22B-Thinking",
        "deepseek-ai/DeepSeek-V3",
        "deepseek-ai/DeepSeek-V3.1-Terminus"
    ]

    # Generate permutations
    permutations = generate_permutations(api_key_list, model_name_list)

    # Write to YAML file
    write_yaml_file(permutations, 'model_config.yaml')

    print(f"\nGenerated {len(permutations)} configurations:")
    for item in permutations:
        print(f"- Model: {item['model_name']}, API Key: {item['litellm_params']['api_key']}")

if __name__ == "__main__":
    main()