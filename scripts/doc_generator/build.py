"""Master assembler script to generate CODEXA_COMPLETE_INTERNAL_DOCUMENTATION.md."""

import os
import re
import sys
from pathlib import Path

# Add scripts/doc_generator to sys.path
sys.path.insert(0, str(Path(__file__).parent))

from part1_core import get_part1
from part2_agents_models import get_part2
from part3_graph_memory import get_part3
from part4_execution_safety import get_part4
from part5_features import get_part5
from part6_functions import get_part6
from part7_audit_tests import get_part7
from part8_synthesis import get_part8

def assemble():
    print("Assembling documentation parts...")
    parts = [
        get_part1(),
        get_part2(),
        get_part3(),
        get_part4(),
        get_part5(),
        get_part6(),
        get_part7(),
        get_part8(),
    ]
    full_doc = "\n\n".join(parts)
    
    target_path = Path("CODEXA_COMPLETE_INTERNAL_DOCUMENTATION.md")
    target_path.write_text(full_doc, encoding="utf-8")
    
    # Analyze output
    char_count = len(full_doc)
    word_count = len(full_doc.split())
    lines = full_doc.splitlines()
    line_count = len(lines)
    
    # Check all 46 sections exist
    section_patterns = [f"## {i}." for i in range(1, 47)]
    missing_sections = []
    for sec in section_patterns:
        if not any(line.strip().startswith(sec) for line in lines):
            missing_sections.append(sec)
            
    print("=" * 60)
    print(f"File created: {target_path.resolve()}")
    print(f"Total Characters: {char_count:,}")
    print(f"Total Words:      {word_count:,}")
    print(f"Total Lines:      {line_count:,}")
    print(f"Target Word Count: >= 12,000 words (Preferred 15,000 - 25,000+)")
    print(f"Missing Sections: {missing_sections if missing_sections else 'None (All 46 sections verified!)'}")
    print("=" * 60)
    
    if word_count < 12000:
        raise ValueError(f"Word count {word_count} is below required 12,000 threshold!")
    if missing_sections:
        raise ValueError(f"Missing sections: {missing_sections}")
    print("Documentation build completed successfully!")

if __name__ == '__main__':
    assemble()
