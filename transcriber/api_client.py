import os
import time
import json
import logging
import requests
try:
    import tiktoken
    TIKTOKEN_AVAILABLE = True
except ImportError:
    TIKTOKEN_AVAILABLE = False
    tiktoken = None
from typing import Dict, Any, Optional, Tuple
from django.conf import settings
from openai import OpenAI, APIError, RateLimitError, AuthenticationError


logger = logging.getLogger(__name__)


class TranscriptionError(Exception):
    """Custom exception for transcription errors."""
    pass


class SummarizationError(Exception):
    """Custom exception for summarization errors."""
    pass


class APIClient:
    """Unified API client for handling OpenAI and DeepSeek API calls."""

    @staticmethod
    def _mask_api_key(api_key: str) -> str:
        """Return a safe representation of API key for logs."""
        if not api_key:
            return "<empty>"
        if len(api_key) <= 12:
            return f"{api_key[:4]}..."
        return f"{api_key[:10]}...{api_key[-4:]} (len={len(api_key)})"
    
    def __init__(self, provider: str = 'openai'):
        """
        Initialize API client with specified provider.
        
        Args:
            provider: 'openai' or 'deepseek'
        """
        self.provider = provider
        self.retry_max = 3
        self.retry_delay = 1  # seconds
        
        if provider == 'openai' and not settings.OPENAI_API_KEY:
            raise ValueError("OpenAI API key not configured")
        elif provider == 'deepseek' and not settings.DEEPSEEK_API_KEY:
            raise ValueError("DeepSeek API key not configured")
    
    def _get_openai_client(self):
        """Get OpenAI client instance."""
        if not hasattr(self, '_openai_client'):
            logger.info(
                "Initializing OpenAI client with key: %s",
                self._mask_api_key(settings.OPENAI_API_KEY),
            )
            # Initialize OpenAI client with explicit configuration
            # to avoid proxy-related issues
            try:
                # Try initializing without any proxy configuration
                self._openai_client = OpenAI(
                    api_key=settings.OPENAI_API_KEY,
                )
            except TypeError as e:
                if 'proxies' in str(e):
                    # If proxies parameter causes issue, try a different approach
                    # Create a simple client without any extra parameters
                    import httpx
                    from openai import OpenAI as OpenAIClient
                    
                    # Create a basic HTTP client
                    http_client = httpx.Client()
                    
                    # Initialize with http_client parameter
                    self._openai_client = OpenAIClient(
                        api_key=settings.OPENAI_API_KEY,
                        http_client=http_client,
                    )
                else:
                    # Re-raise if it's a different error
                    raise
        return self._openai_client
    
    def transcribe_audio(self, audio_file_path: str) -> Tuple[str, Dict[str, Any]]:
        """
        Transcribe audio file using Whisper API.
        
        Args:
            audio_file_path: Path to the audio file
            
        Returns:
            Tuple of (transcribed_text, metadata)
            
        Raises:
            TranscriptionError: If transcription fails
        """
        if self.provider == 'openai':
            return self._transcribe_with_openai(audio_file_path)
        elif self.provider == 'deepseek':
            return self._transcribe_with_deepseek(audio_file_path)
        else:
            raise ValueError(f"Unsupported provider: {self.provider}")
    
    def _transcribe_with_openai(self, audio_file_path: str) -> Tuple[str, Dict[str, Any]]:
        """Transcribe using OpenAI Whisper API."""
        logger.info(
            "Transcription request key in use: %s",
            self._mask_api_key(settings.OPENAI_API_KEY),
        )
        for attempt in range(self.retry_max):
            try:
                with open(audio_file_path, 'rb') as audio_file:
                    response = self._get_openai_client().audio.transcriptions.create(
                        model=settings.WHISPER_MODEL,
                        file=audio_file,
                        response_format="verbose_json"
                    )
                
                # Extract transcription and metadata (compatible with object/dict response segments)
                transcribed_text = getattr(response, 'text', '') or ''
                raw_segments = getattr(response, 'segments', None) or []
                parsed_segments = []

                for segment in raw_segments:
                    if isinstance(segment, dict):
                        parsed_segments.append({
                            'id': segment.get('id'),
                            'start': segment.get('start'),
                            'end': segment.get('end'),
                            'text': segment.get('text', ''),
                        })
                    else:
                        parsed_segments.append({
                            'id': getattr(segment, 'id', None),
                            'start': getattr(segment, 'start', None),
                            'end': getattr(segment, 'end', None),
                            'text': getattr(segment, 'text', ''),
                        })

                metadata = {
                    'language': getattr(response, 'language', None),
                    'duration': getattr(response, 'duration', None),
                    'segments': parsed_segments,
                }
                
                return transcribed_text, metadata
                
            except RateLimitError as e:
                if attempt < self.retry_max - 1:
                    time.sleep(self.retry_delay * (2 ** attempt))
                    continue
                raise TranscriptionError(f"Rate limit exceeded: {str(e)}")
            except AuthenticationError as e:
                raise TranscriptionError(f"Authentication failed: {str(e)}")
            except APIError as e:
                if attempt < self.retry_max - 1:
                    time.sleep(self.retry_delay * (2 ** attempt))
                    continue
                raise TranscriptionError(f"OpenAI API error: {str(e)}")
            except Exception as e:
                raise TranscriptionError(f"Transcription failed: {str(e)}")
    
    def _transcribe_with_deepseek(self, audio_file_path: str) -> Tuple[str, Dict[str, Any]]:
        """Transcribe using DeepSeek API (if supported)."""
        # Note: DeepSeek may not have direct audio transcription API
        # For now, we'll raise an error or implement alternative
        raise TranscriptionError("DeepSeek audio transcription not yet implemented. Please use OpenAI provider.")
    
    def summarize_text(self, text: str, style: str = 'concise') -> Tuple[str, Dict[str, Any]]:
        """
        Summarize text using the configured API provider.
        
        Args:
            text: Text to summarize
            style: Summary style ('concise', 'detailed', 'bullet_points', 'key_takeaways')
            
        Returns:
            Tuple of (summary_text, token_usage)
            
        Raises:
            SummarizationError: If summarization fails
        """
        if self.provider == 'openai':
            return self._summarize_with_openai(text, style)
        elif self.provider == 'deepseek':
            return self._summarize_with_deepseek(text, style)
        else:
            raise ValueError(f"Unsupported provider: {self.provider}")
    
    def _summarize_with_openai(self, text: str, style: str) -> Tuple[str, Dict[str, Any]]:
        """Summarize using OpenAI Chat Completion API."""
        # Define system prompts based on style
        system_prompts = {
            'concise': "Summarize the following text in 2-3 concise sentences, capturing only the most important points.",
            'detailed': "Provide a comprehensive, detailed summary of the following text. Include all key points, supporting details, and main arguments.",
            'bullet_points': "Summarize the following text using 5-7 bullet points. Each bullet should highlight a key idea or important detail.",
            'key_takeaways': "Extract the most important insights and key takeaways from the following text. Present them as actionable insights.",
        }
        
        system_prompt = system_prompts.get(style, system_prompts['concise'])
        
        for attempt in range(self.retry_max):
            try:
                response = self._get_openai_client().chat.completions.create(
                    model=settings.SUMMARY_MODEL,
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": text}
                    ],
                    max_tokens=1000,
                    temperature=0.7,
                )
                
                summary = response.choices[0].message.content
                token_usage = {
                    'prompt_tokens': response.usage.prompt_tokens,
                    'completion_tokens': response.usage.completion_tokens,
                    'total_tokens': response.usage.total_tokens,
                }
                
                return summary, token_usage
                
            except RateLimitError as e:
                if attempt < self.retry_max - 1:
                    time.sleep(self.retry_delay * (2 ** attempt))
                    continue
                raise SummarizationError(f"Rate limit exceeded: {str(e)}")
            except AuthenticationError as e:
                raise SummarizationError(f"Authentication failed: {str(e)}")
            except APIError as e:
                if attempt < self.retry_max - 1:
                    time.sleep(self.retry_delay * (2 ** attempt))
                    continue
                raise SummarizationError(f"OpenAI API error: {str(e)}")
            except Exception as e:
                raise SummarizationError(f"Summarization failed: {str(e)}")
    
    def _summarize_with_deepseek(self, text: str, style: str) -> Tuple[str, Dict[str, Any]]:
        """Summarize using DeepSeek API."""
        # Define system prompts based on style
        system_prompts = {
            'concise': "Summarize the following text in 2-3 concise sentences, capturing only the most important points.",
            'detailed': "Provide a comprehensive, detailed summary of the following text. Include all key points, supporting details, and main arguments.",
            'bullet_points': "Summarize the following text using 5-7 bullet points. Each bullet should highlight a key idea or important detail.",
            'key_takeaways': "Extract the most important insights and key takeaways from the following text. Present them as actionable insights.",
        }
        
        system_prompt = system_prompts.get(style, system_prompts['concise'])
        
        headers = {
            'Authorization': f'Bearer {settings.DEEPSEEK_API_KEY}',
            'Content-Type': 'application/json',
        }
        
        data = {
            'model': 'deepseek-chat',
            'messages': [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": text}
            ],
            'max_tokens': 1000,
            'temperature': 0.7,
        }
        
        for attempt in range(self.retry_max):
            try:
                response = requests.post(
                    f'{settings.DEEPSEEK_BASE_URL}/chat/completions',
                    headers=headers,
                    json=data,
                    timeout=30
                )
                
                if response.status_code != 200:
                    if response.status_code == 429 and attempt < self.retry_max - 1:
                        time.sleep(self.retry_delay * (2 ** attempt))
                        continue
                    raise SummarizationError(f"DeepSeek API error: {response.status_code} - {response.text}")
                
                result = response.json()
                summary = result['choices'][0]['message']['content']
                token_usage = {
                    'prompt_tokens': result['usage']['prompt_tokens'],
                    'completion_tokens': result['usage']['completion_tokens'],
                    'total_tokens': result['usage']['total_tokens'],
                }
                
                return summary, token_usage
                
            except requests.exceptions.RequestException as e:
                if attempt < self.retry_max - 1:
                    time.sleep(self.retry_delay * (2 ** attempt))
                    continue
                raise SummarizationError(f"Network error: {str(e)}")
            except Exception as e:
                raise SummarizationError(f"DeepSeek summarization failed: {str(e)}")
    
    def calculate_cost(self, token_usage: Dict[str, int]) -> float:
        """
        Calculate cost based on token usage and provider.
        
        Args:
            token_usage: Dictionary with 'prompt_tokens' and 'completion_tokens'
            
        Returns:
            Cost in USD
        """
        prompt_tokens = token_usage.get('prompt_tokens', 0)
        completion_tokens = token_usage.get('completion_tokens', 0)
        
        if self.provider == 'openai':
            cost = (prompt_tokens / 1000 * settings.OPENAI_COST_INPUT +
                   completion_tokens / 1000 * settings.OPENAI_COST_OUTPUT)
        elif self.provider == 'deepseek':
            cost = (prompt_tokens / 1000 * settings.DEEPSEEK_COST_INPUT +
                   completion_tokens / 1000 * settings.DEEPSEEK_COST_OUTPUT)
        else:
            cost = 0.0
        
        return cost
    
    def estimate_cost_from_text(self, text: str, style: str = 'concise') -> float:
        """
        Estimate cost for summarizing text.
        
        Args:
            text: Text to summarize
            style: Summary style
            
        Returns:
            Estimated cost in USD
        """
        # Count tokens in input text
        if TIKTOKEN_AVAILABLE and tiktoken:
            try:
                encoding = tiktoken.encoding_for_model("gpt-3.5-turbo")
                input_tokens = len(encoding.encode(text))
            except Exception:
                # Fallback to word count estimation
                word_count = len(text.split())
                input_tokens = int(word_count * 1.3)  # Rough estimate
        else:
            # Fallback to word count estimation
            word_count = len(text.split())
            input_tokens = int(word_count * 1.3)  # Rough estimate
        
        # Estimate output tokens based on style
        output_estimates = {
            'concise': 100,  # ~2-3 sentences
            'detailed': 300,  # ~comprehensive summary
            'bullet_points': 200,  # ~5-7 bullet points
            'key_takeaways': 150,  # ~actionable insights
        }
        output_tokens = output_estimates.get(style, 100)
        
        token_usage = {
            'prompt_tokens': input_tokens,
            'completion_tokens': output_tokens,
        }
        
        return self.calculate_cost(token_usage)
    
    def switch_provider(self, new_provider: str):
        """Switch to a different API provider."""
        if new_provider not in ['openai', 'deepseek']:
            raise ValueError(f"Unsupported provider: {new_provider}")
        
        if new_provider == 'openai' and not settings.OPENAI_API_KEY:
            raise ValueError("OpenAI API key not configured")
        elif new_provider == 'deepseek' and not settings.DEEPSEEK_API_KEY:
            raise ValueError("DeepSeek API key not configured")
        
        self.provider = new_provider
