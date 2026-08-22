import re

class UnknownValReplacer:
    def __init__(self, prefix="input"):
        self.counter = 1
        self.prefix = prefix
        self.pattern = r"(\d*)'bx"
    
    def needs_replace(self, text):
        return bool(re.search(self.pattern, text))
    
    def replace(self, text):
        if not self.needs_replace(text):
            return None
            
        current_input = f"{self.prefix}{self.counter}"
        self.counter += 1
        replaced_text = re.sub(self.pattern, current_input, text)
        return replaced_text, current_input
    
    def reset(self):
        self.counter = 1