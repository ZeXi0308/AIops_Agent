from typing import Dict, Any
from langchain_core.messages.utils import trim_messages, count_tokens_approximately


class MessageTrimmer:
    """Message trimming utility class that sets different parameters based on LLM name"""
    
    def __init__(self):
        # Predefined parameter configurations for different LLMs
        self.llm_configs = {
            "gpt-4": {
                "strategy": "last",
                "max_tokens": 5000,
                "start_on": "human",
                "end_on": ("human", "tool")
            },
            "gpt-3.5": {
                "strategy": "last", 
                "max_tokens": 5000,
                "start_on": "human",
                "end_on": ("human", "tool")
            },
            "claude": {
                "strategy": "last",
                "max_tokens": 5000,
                "start_on": "human", 
                "end_on": ("human", "tool")
            },
            "default": {
                "strategy": "last",
                "max_tokens": 5000,
                "start_on": "human",
                "end_on": ("human", "tool")
            }
        }
    
    def trim_messages_of_llm(self, messages: list, llm_name: str) -> list:
        """
        Trim messages based on LLM name
        
        Args:
            messages: List of messages
            llm_name: LLM name
            
        Returns:
            Trimmed message list
        """
        config = self.llm_configs.get(llm_name.lower(), self.llm_configs["default"])
        
        return trim_messages(
            messages,
            strategy=config["strategy"],
            token_counter=count_tokens_approximately,
            max_tokens=config["max_tokens"],
            start_on=config["start_on"],
            end_on=config["end_on"]
        )
    
    def add_llm_config(self, llm_name: str, config: Dict[str, Any]):
        """Add new LLM configuration"""
        self.llm_configs[llm_name.lower()] = config
    
    def get_llm_config(self, llm_name: str) -> Dict[str, Any]:
        """Get LLM configuration"""
        return self.llm_configs.get(llm_name.lower(), self.llm_configs["default"])