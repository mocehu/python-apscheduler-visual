"""
Docstring parser module supporting Google, NumPy, and Sphinx/reST formats.
"""

import re
from typing import Dict, List, Optional, Tuple


def parse_google_docstring(docstring: str) -> Tuple[str, Dict[str, Dict[str, str]]]:
    """
    Parse Google-style docstring.
    
    Example:
        '''Short description.
        
        Longer description here.
        
        Args:
            param1 (int): Description of param1.
            param2 (str, optional): Description of param2.
                Defaults to "default".
        
        Returns:
            bool: Description of return value.
        '''
    """
    if not docstring:
        return "", {}
    
    lines = docstring.strip().split('\n')
    description_lines = []
    params = {}
    
    in_args = False
    in_description = True
    current_param = None
    current_param_lines = []
    
    section_keywords = ('Args:', 'Arguments:', 'Returns:', 'Raises:', 'Yields:', 
                         'Note:', 'Example:', 'Examples:', 'Attributes:', 'See Also:')
    
    for i, line in enumerate(lines):
        stripped = line.strip()
        
        if any(stripped.startswith(kw) or stripped.lower().startswith(kw.lower()) for kw in section_keywords):
            if current_param:
                params[current_param]['description'] = ' '.join(current_param_lines).strip()
                current_param = None
                current_param_lines = []
            in_description = False
            if stripped.lower().startswith(('args:', 'arguments:')):
                in_args = True
            else:
                in_args = False
            continue
        
        if in_description:
            if stripped:
                description_lines.append(stripped)
        elif in_args:
            param_match = re.match(r'^(\w+)\s*(?:\(([^)]+)\))?\s*:\s*(.*)$', stripped)
            if param_match:
                if current_param:
                    params[current_param]['description'] = ' '.join(current_param_lines).strip()
                
                param_name = param_match.group(1)
                param_type = param_match.group(2) or ''
                param_desc = param_match.group(3) or ''
                
                params[param_name] = {
                    'type': param_type.strip(),
                    'description': param_desc.strip()
                }
                current_param = param_name
                current_param_lines = [param_desc] if param_desc else []
            elif current_param and (line.startswith(' ') or line.startswith('\t') or not stripped):
                if stripped:
                    current_param_lines.append(stripped)
    
    if current_param and current_param_lines:
        params[current_param]['description'] = ' '.join(current_param_lines).strip()
    
    description = ' '.join(description_lines).strip()
    return description, params


def parse_numpy_docstring(docstring: str) -> Tuple[str, Dict[str, Dict[str, str]]]:
    """
    Parse NumPy-style docstring.
    
    Example:
        '''Short description.
        
        Longer description here.
        
        Parameters
        ----------
        param1 : int
            Description of param1.
        param2 : str, optional
            Description of param2.
        
        Returns
        -------
        bool
            Description of return value.
        '''
    """
    if not docstring:
        return "", {}
    
    lines = docstring.strip().split('\n')
    description_lines = []
    params = {}
    
    in_params = False
    in_description = True
    current_param = None
    current_param_lines = []
    
    section_pattern = re.compile(r'^([A-Z][a-zA-Z]+)\s*$')
    underline_pattern = re.compile(r'^[-=]+\s*$')
    
    i = 0
    while i < len(lines):
        line = lines[i]
        stripped = line.strip()
        
        if section_pattern.match(stripped):
            section_name = stripped.lower()
            if current_param:
                params[current_param]['description'] = ' '.join(current_param_lines).strip()
                current_param = None
                current_param_lines = []
            
            i += 1
            if i < len(lines) and underline_pattern.match(lines[i].strip()):
                i += 1
            
            if section_name == 'parameters':
                in_params = True
                in_description = False
            else:
                in_params = False
                in_description = False
            continue
        
        if in_description:
            if stripped:
                description_lines.append(stripped)
        elif in_params:
            param_match = re.match(r'^(\w+)\s*:\s*([^,\n]+(?:,\s*optional)?)\s*$', stripped)
            if param_match:
                if current_param:
                    params[current_param]['description'] = ' '.join(current_param_lines).strip()
                
                param_name = param_match.group(1)
                param_type = param_match.group(2).strip()
                
                params[param_name] = {
                    'type': param_type,
                    'description': ''
                }
                current_param = param_name
                current_param_lines = []
            elif current_param and (line.startswith(' ') or line.startswith('\t')):
                if stripped:
                    current_param_lines.append(stripped)
        
        i += 1
    
    if current_param and current_param_lines:
        params[current_param]['description'] = ' '.join(current_param_lines).strip()
    
    description = ' '.join(description_lines).strip()
    return description, params


def parse_sphinx_docstring(docstring: str) -> Tuple[str, Dict[str, Dict[str, str]]]:
    """
    Parse Sphinx/reST-style docstring.
    
    Example:
        '''Short description.
        
        Longer description here.
        
        :param param1: Description of param1.
        :type param1: int
        :param param2: Description of param2.
        :type param2: str
        :returns: Description of return value.
        :rtype: bool
        '''
    """
    if not docstring:
        return "", {}
    
    lines = docstring.strip().split('\n')
    description_lines = []
    params = {}
    
    param_pattern = re.compile(r'^:param\s+(\w+)\s*:\s*(.*)$')
    type_pattern = re.compile(r'^:type\s+(\w+)\s*:\s*(.*)$')
    
    for line in lines:
        stripped = line.strip()
        
        param_match = param_pattern.match(stripped)
        type_match = type_pattern.match(stripped)
        
        if param_match:
            param_name = param_match.group(1)
            param_desc = param_match.group(2).strip()
            if param_name not in params:
                params[param_name] = {'type': '', 'description': ''}
            params[param_name]['description'] = param_desc
        elif type_match:
            param_name = type_match.group(1)
            param_type = type_match.group(2).strip()
            if param_name not in params:
                params[param_name] = {'type': '', 'description': ''}
            params[param_name]['type'] = param_type
        elif stripped and not stripped.startswith(':'):
            description_lines.append(stripped)
    
    description = ' '.join(description_lines).strip()
    return description, params


def detect_docstring_style(docstring: str) -> str:
    """
    Detect the docstring style based on content patterns.
    
    Returns:
        'google', 'numpy', 'sphinx', or 'auto'
    """
    if not docstring:
        return 'auto'
    
    lines = docstring.strip().split('\n')
    
    for line in lines:
        stripped = line.strip().lower()
        
        if stripped.startswith('args:') or stripped.startswith('arguments:'):
            return 'google'
        
        if stripped == 'parameters' or stripped == 'parameters:':
            return 'numpy'
        
        if stripped.startswith(':param ') or stripped.startswith(':type '):
            return 'sphinx'
    
    underline_pattern = re.compile(r'^[-=]+\s*$')
    for i, line in enumerate(lines):
        stripped = line.strip()
        if underline_pattern.match(stripped) and i > 0:
            prev_line = lines[i - 1].strip().lower()
            if prev_line == 'parameters':
                return 'numpy'
    
    return 'auto'


def parse_docstring(docstring: str, style: str = 'auto') -> Tuple[str, Dict[str, Dict[str, str]]]:
    """
    Parse a docstring and extract description and parameter information.
    
    Args:
        docstring: The docstring to parse.
        style: The docstring style ('google', 'numpy', 'sphinx', 'auto').
               If 'auto', will attempt to detect the style.
    
    Returns:
        Tuple of (description, params_dict) where params_dict is:
        {
            'param_name': {
                'type': 'param_type',
                'description': 'param_description'
            }
        }
    """
    if not docstring:
        return "", {}
    
    if style == 'auto':
        style = detect_docstring_style(docstring)
    
    if style == 'google':
        return parse_google_docstring(docstring)
    elif style == 'numpy':
        return parse_numpy_docstring(docstring)
    elif style == 'sphinx':
        return parse_sphinx_docstring(docstring)
    else:
        desc_google, params_google = parse_google_docstring(docstring)
        if params_google:
            return desc_google, params_google
        
        desc_numpy, params_numpy = parse_numpy_docstring(docstring)
        if params_numpy:
            return desc_numpy, params_numpy
        
        desc_sphinx, params_sphinx = parse_sphinx_docstring(docstring)
        if params_sphinx:
            return desc_sphinx, params_sphinx
        
        lines = docstring.strip().split('\n')
        description = ' '.join(line.strip() for line in lines if line.strip())
        return description, {}


def extract_function_description(docstring: str) -> str:
    """
    Extract only the function description from a docstring.
    
    Args:
        docstring: The docstring to parse.
    
    Returns:
        The function description (first paragraph before any section headers).
    """
    if not docstring:
        return ""
    
    description, _ = parse_docstring(docstring)
    return description


def extract_param_descriptions(docstring: str) -> Dict[str, str]:
    """
    Extract only parameter descriptions from a docstring.
    
    Args:
        docstring: The docstring to parse.
    
    Returns:
        Dict mapping parameter names to their descriptions.
    """
    if not docstring:
        return {}
    
    _, params = parse_docstring(docstring)
    return {name: info.get('description', '') for name, info in params.items()}


def extract_param_info(docstring: str) -> Dict[str, Dict[str, str]]:
    """
    Extract full parameter info (type and description) from a docstring.
    
    Args:
        docstring: The docstring to parse.
    
    Returns:
        Dict mapping parameter names to their info (type and description).
    """
    if not docstring:
        return {}
    
    _, params = parse_docstring(docstring)
    return params