import discord
from discord.ext import commands
import requests
import os
import shutil
import time

# Function to load API keys from a file
def load_api_keys(filename):
    with open(filename, 'r') as file:
        keys = file.readlines()
    discord_key = keys[0].strip()
    gpt_key = keys[1].strip()
    return discord_key, gpt_key

# Function to load identity and context from a file
def load_identity_and_context(filename):
    with open(filename, 'r') as file:
        lines = file.readlines()
    target_user_id = lines[0].strip()
    voice = lines[1].strip()
    context = ''.join(lines[2:]).strip()  # Remaining lines as context
    return target_user_id, voice, context

# Function to update the context in the file
def update_context(filename, new_context):
    with open(filename, 'a') as file:
        file.write(f"\n{new_context}")

# Load API keys and context
discord_key, gpt_key = load_api_keys('apiKeys.txt')
target_user_id, voice, context = load_identity_and_context('NHP_Identity.txt')

# Set up OpenAI API key
headers = {
    'Authorization': f'Bearer {gpt_key}',
    'Content-Type': 'application/json'
}

# Set up Discord bot with necessary intents
intents = discord.Intents.default()
intents.message_content = True
intents.members = True
intents.presences = True
bot = commands.Bot(command_prefix="!", intents=intents)

# Flag to track recording state
bot.is_recording = False

# Hardcoded directory path for saving files
#output_directory = 
#put where you want the program to take and use files from here
@bot.event
async def on_ready():
    print(f'Bot is ready as {bot.user}')
    # List the users in the voice channel
    for guild in bot.guilds:
        for vc in guild.voice_channels:
            members = [f"{member.display_name}, ID: {member.id}" for member in vc.members]
            if members:
                print(f"Users in the voice channel:\n- " + "\n- ".join(members))

@bot.command()
async def j(ctx):
    if ctx.author.voice:
        channel = ctx.author.voice.channel
        if not ctx.voice_client or not ctx.voice_client.is_connected():
            await channel.connect()
        else:
            await ctx.send("Already connected to a voice channel.")

@bot.command()
async def l(ctx):
    if ctx.voice_client:
        await ctx.voice_client.disconnect()

@bot.command()
async def sr(ctx):
    if ctx.voice_client and ctx.voice_client.is_connected():
        ctx.voice_client.start_recording(discord.sinks.MP3Sink(), finished_callback, ctx)
        bot.is_recording = True
        await ctx.send("Recording...")
        print("Recording started...")
    else:
        await ctx.send("Bot is not connected to a voice channel. Use !j to connect the bot to a voice channel.")

async def finished_callback(sink, ctx):
    global context 
    bot.is_recording = False
    print("Recording stopped...")
    recorded_users = [f"<@{user_id}>" for user_id, audio in sink.audio_data.items()]
    files = [discord.File(audio.file, f"{user_id}.{sink.encoding}") for user_id, audio in sink.audio_data.items()]
    await ctx.channel.send(f"Finished! Recorded audio for {', '.join(recorded_users)}.", files=files)

    for user_id, audio in sink.audio_data.items():
        file_path = os.path.join(output_directory, f"{user_id}.{sink.encoding}")
        audio.file.seek(0) 
        with open(file_path, "wb") as f:
            shutil.copyfileobj(audio.file, f)
        print(f"File saved to {file_path}")

        time.sleep(2)

        try:
            if os.path.exists(file_path) and os.path.getsize(file_path) > 0:
                print(f"File {file_path} exists and is not empty.")
                if str(user_id) == target_user_id:
                # Transcribe audio file using OpenAI Whisper API
                    transcribe_url = "https://api.openai.com/v1/audio/transcriptions"
                    with open(file_path, "rb") as audio_file:
                        response = requests.post(transcribe_url, headers={
                            'Authorization': f'Bearer {gpt_key}'
                        }, files={
                            'file': audio_file
                        }, data={
                            'model': 'whisper-1'
                        })

                    if response.status_code == 200:
                        text = response.json()['text']
                        print(f"Recognized: {text}")

                    
                    
                        # Generate GPT-4 response
                        gpt_response = requests.post('https://api.openai.com/v1/chat/completions', headers=headers, json={
                            'model': 'gpt-4',
                            'messages': [
                                {"role": "system", "content": context},
                                {"role": "user", "content": text}
                            ]
                        })

                        if gpt_response.status_code == 200:
                            gpt_text = gpt_response.json()['choices'][0]['message']['content'].strip()
                            print(f"GPT-4 Response: {gpt_text}")

                            # Append to context and update the file
                            update_context('NHP_Identity.txt', f"\nUser: {text}\nAI: {gpt_text}")
                            context += f"\nUser: {text}\nAI: {gpt_text}"

                            # Generate speech from GPT-4 response
                            tts_response = requests.post('https://api.openai.com/v1/audio/speech', headers=headers, json={
                                'model': 'tts-1',
                                'input': gpt_text,
                                'voice': voice,
                                'response_format': 'mp3'
                            })

                            if tts_response.status_code == 200:
                                tts_output_path = os.path.join(output_directory, "output.mp3")
                                with open(tts_output_path, "wb") as out:
                                    out.write(tts_response.content)

                                print(f"Saving TTS output to: {tts_output_path}")

                                # Check if the output file exists
                                if os.path.exists(tts_output_path) and os.path.getsize(tts_output_path) > 0:
                                    print(f"TTS output file {tts_output_path} exists and is not empty.")

                                    # Play the audio file
                                    voice_client = ctx.voice_client
                                    if voice_client.is_connected():
                                        voice_client.play(discord.FFmpegPCMAudio(tts_output_path))
                                    else:
                                        await ctx.send("The bot is not connected to a voice channel.")
                                else:
                                    print(f"TTS output file {tts_output_path} does not exist or is empty.")
                            else:
                                print(f"Error generating speech: {tts_response.json()}")
                        else:
                            print(f"Error generating GPT-4 response: {gpt_response.json()}")
                    else:
                        print(f"User '{user_id}' not recognized in the audio.")
                else:
                    print(f"Error transcribing audio: {response.json()}")
            else:
                print(f"File {file_path} does not exist or is empty.")
        except Exception as e:
            print(f"Error processing file {file_path}: {str(e)}")

@bot.command()
async def st(ctx):
    if bot.is_recording:
        ctx.voice_client.stop_recording()  # Stop the recording, finished_callback will shortly after be called
        await ctx.send("Stopped!")
        print("Recording stopped command issued...")
    else:
        await ctx.send("The bot is not recording.")

# Start the bot using the loaded Discord API key
bot.run(discord_key)