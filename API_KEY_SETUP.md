# OpenAI API Key Setup Instructions

## Problem Identified
The application is failing with the error:
```
Authentication failed: Error code: 401 - {'error': {'message': 'Incorrect API key provided: sk-your-***************here'...}}
```

This indicates that the OpenAI API key in your `.env` file is either:
1. Invalid or incorrect format
2. Expired
3. Has insufficient credits

## Solution: Get a Valid OpenAI API Key

### Step 1: Get Your OpenAI API Key
1. Go to https://platform.openai.com/api-keys
2. Sign in with your OpenAI account
3. Click "Create new secret key"
4. Give it a name (e.g., "Audio Summarizer")
5. Copy the key immediately (you won't be able to see it again)

### Step 2: Check Key Format
A valid OpenAI API key should:
- Start with `sk-` (not `sk-proj-`, `sk-your-`, or any other prefix)
- Be approximately **51 characters** long (newer keys) or **64 characters** (older keys)
- Contain only alphanumeric characters (a-z, A-Z, 0-9) and possibly hyphens
- NOT contain underscores or special characters beyond hyphens

**Example of a valid key:**
```
sk-abc123def456ghi789jkl012mno345pqr678stu901vwx234yz567
```

### Step 3: Update Your .env File
1. Open `audio_summarizer/.env` in a text editor
2. Find the line that says:
   ```
   OPENAI_API_KEY=sk-your-actual-openai-api-key-here
   ```
3. Replace it with your actual key:
   ```
   OPENAI_API_KEY=sk-abc123def456ghi789jkl012mno345pqr678stu901vwx234yz567
   ```
   (Use your actual key, not this example)

### Step 4: Restart the Application
After updating the `.env` file, you need to restart the Django server:

1. **Stop the current server** (Ctrl+C in the terminal where it's running)
2. **Start it again**:
   ```bash
   cd audio_summarizer
   python manage.py runserver
   ```

### Step 5: Test the API Key
Run the test script to verify your key works:
```bash
cd audio_summarizer
python test_api_key.py
```

You should see:
```
Testing OpenAI API key...
API key loaded: sk-abc123def4...
Key length: 51 characters

Testing API key with OpenAI client...
Making test API call to list models...
SUCCESS: API key is valid! Found 120 models.
```

## Troubleshooting

### If you still get authentication errors:

1. **Check your OpenAI account balance:**
   - Go to https://platform.openai.com/usage
   - Ensure you have credits available

2. **Verify key permissions:**
   - Make sure the key has not been revoked
   - Check if there are any usage limits on the key

3. **Try creating a new key:**
   - Sometimes keys can become corrupted or have issues
   - Create a fresh key and update the `.env` file

4. **Check for whitespace:**
   - Make sure there are no extra spaces before or after the key in the `.env` file
   - The line should be exactly: `OPENAI_API_KEY=your-key-here`

5. **Restart all services:**
   - Stop both Django server and Celery worker
   - Start them fresh after updating the `.env` file

## Alternative: Use DeepSeek API
If you cannot get OpenAI API to work, you can use DeepSeek API instead:

1. Get a DeepSeek API key from https://platform.deepseek.com/api-keys
2. Update your `.env` file:
   ```
   DEFAULT_API_PROVIDER=deepseek
   DEEPSEEK_API_KEY=your-deepseek-key-here
   ```
3. Note: DeepSeek does **not** support audio transcription, only text summarization
   - You would need to provide pre-transcribed text
   - Or use a different service for transcription

## Need Help?
If you continue to experience issues:
1. Check the `logs/django.log` file for detailed error messages
2. Verify your internet connection can reach OpenAI's API
3. Ensure your firewall or proxy isn't blocking API requests

## Important Notes
- **Costs**: Using OpenAI API incurs costs. Check pricing at https://openai.com/pricing
- **Rate Limits**: Free tier accounts have rate limits
- **Security**: Never commit your `.env` file to version control
- **Backup**: Keep a backup of your API key in a secure location