from openai import OpenAI
import sys
import json
import pandas as pd
import numpy as np
import os

# Try importing prompts with fallback
# I honestly don't know why this doesn't work properly
try:
    import prompts
except ModuleNotFoundError:
    # If running in interactive mode, try different paths
    sys.path.append('.')
    sys.path.append('./cxr_audit')
    import prompts
    

def gradeLunit(self, rpt):
    subs = {
        'rpt': rpt
    }
    prompt_grade_chat_msg = self.create_chat_message(role="user", content=prompts.prompt_get_lunit_findings.substitute(subs))
    messages_lst = [self.sys_role_chat_msg, prompt_grade_chat_msg]

    return getLLMJSON(messages_lst, self.client, self.model_name, prompts.cxrGrade)