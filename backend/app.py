# backend/app.py
import os
import traceback
import yt_dlp
import cv2
import numpy as np
from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
from moviepy.editor import VideoFileClip
from youtube_transcript_api import YouTubeTranscriptApi
from PIL import Image, ImageDraw, ImageFont
import textwrap

app = Flask(__name__)
CORS(app)

# --- Configuration ---
TEMP_VIDEO_FOLDER = 'temp_videos'
GIF_OUTPUT_FOLDER = 'static/gifs'
app.config['GIF_OUTPUT_FOLDER'] = GIF_OUTPUT_FOLDER

# --- Ensure Folders Exist ---
if not os.path.exists(TEMP_VIDEO_FOLDER):
    os.makedirs(TEMP_VIDEO_FOLDER)
if not os.path.exists(GIF_OUTPUT_FOLDER):
    os.makedirs(GIF_OUTPUT_FOLDER)

# --- Helper Functions ---

def get_video_transcript(video_id):
    try:
        transcript_list = YouTubeTranscriptApi.list_transcripts(video_id)
        try:
            transcript = transcript_list.find_transcript(['en'])
        except:
            transcript = transcript_list.find_transcript([t.language_code for t in transcript_list])
        return transcript.fetch()
    except Exception as e:
        print(f"!!! Could not get transcript. Error: {e}")
        return None

def find_relevant_segments(transcript, prompt, count=3):
    stop_words = {'the', 'is', 'to', 'and', 'or', 'but', 'in', 'on', 'at', 'by', 'for', 'with', 'about', 'a', 'an', 'of', 'that', 'this', 'it', 'be', 'are', 'was', 'were', 'been', 'have', 'has', 'had', 'do', 'does', 'did', 'will', 'would', 'should', 'could', 'can', 'may', 'might', 'must', 'shall', 'i', 'you', 'he', 'she', 'we', 'they', 'me', 'him', 'her', 'us', 'them'}
    prompt_keywords = set(word.lower() for word in prompt.split() if word.lower() not in stop_words and len(word) > 2)
    scored_segments = []
    for segment in transcript:
        text = segment['text'].lower()
        exact_matches = sum(1 for word in prompt_keywords if word in text.split())
        partial_matches = sum(1 for word in prompt_keywords if word in text)
        total_score = exact_matches * 2 + partial_matches
        if total_score > 0:
            scored_segments.append({'segment': segment, 'score': total_score})

    if len(scored_segments) < count:
        used_start_times = {item['segment']['start'] for item in scored_segments}
        available_segments = [seg for seg in transcript if seg['start'] not in used_start_times]
        if available_segments:
            needed = count - len(scored_segments)
            for seg in available_segments[:needed]:
                scored_segments.append({'segment': seg, 'score': 0})
    
    scored_segments.sort(key=lambda x: x['score'], reverse=True)
    return [item['segment'] for item in scored_segments[:count]]

def add_text_to_frame(frame, text, position='bottom'):
    try:
        frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        pil_image = Image.fromarray(frame_rgb)
        draw = ImageDraw.Draw(pil_image)
        try:
            font = ImageFont.truetype("arial.ttf", 24)
        except IOError:
            font = ImageFont.load_default()
        
        img_width, img_height = pil_image.size
        wrapped_text = textwrap.fill(text, width=int(img_width / 15))
        
        bbox = draw.textbbox((0, 0), wrapped_text, font=font)
        text_width = bbox[2] - bbox[0]
        text_height = bbox[3] - bbox[1]
        
        x = (img_width - text_width) // 2
        y = img_height - text_height - 25
        
        outline_range = 2
        for dx in range(-outline_range, outline_range + 1):
            for dy in range(-outline_range, outline_range + 1):
                if dx != 0 or dy != 0:
                    draw.text((x + dx, y + dy), wrapped_text, font=font, fill='black')
        
        draw.text((x, y), wrapped_text, font=font, fill='white')
        return cv2.cvtColor(np.array(pil_image), cv2.COLOR_RGB2BGR)
    except Exception as e:
        print(f"DEBUG: Error adding text to frame: {e}")
        return frame

def create_gif_from_segment(video_path, segment, output_filename):
    start_time = segment['start']
    duration = segment['duration']
    end_time = start_time + min(duration, 5)
    text = segment['text']

    try:
        with VideoFileClip(video_path).subclip(start_time, end_time) as video_clip:
            frames_with_text = [add_text_to_frame(cv2.cvtColor(frame, cv2.COLOR_RGB2BGR), text) for frame in video_clip.iter_frames(fps=10)]
            if frames_with_text:
                pil_frames = [Image.fromarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)) for frame in frames_with_text]
                pil_frames[0].save(
                    output_filename, save_all=True, append_images=pil_frames[1:],
                    duration=100, loop=0, optimize=True
                )
                return output_filename
        return None
    except Exception as e:
        print(f"!!! Error creating GIF: {e}")
        return None

# --- Main Route ---
@app.route('/api/generate-gifs', methods=['POST'])
def generate_gifs_route():
    data = request.get_json()
    prompt = data.get('prompt')
    youtube_url = data.get('youtube_url')

    if not prompt or not youtube_url:
        return jsonify({'error': 'Prompt and YouTube URL are required.'}), 400

    try:
        # Final yt-dlp options to mimic a browser as closely as possible
        ydl_opts = {
            'quiet': True,
            'no_warnings': True,
            'format': 'bestvideo[ext=mp4][height<=480]+bestaudio[ext=m4a]/best[ext=mp4][height<=480]/best',
            'http_headers': {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/138.0.0.0 Safari/537.36',
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7',
                'Accept-Language': 'en-US,en;q=0.9',
            },
            'extractor_args': {'youtube': {'player_client': ['web']}}
        }

        # 1. Extract Video Info
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(youtube_url, download=False)
            video_id = info['id']
        
        # 2. Download Video
        video_path_template = os.path.join(TEMP_VIDEO_FOLDER, f"{video_id}.%(ext)s")
        ydl_opts['outtmpl'] = video_path_template
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([youtube_url])

        video_path = next((os.path.join(TEMP_VIDEO_FOLDER, f) for f in os.listdir(TEMP_VIDEO_FOLDER) if f.startswith(video_id)), None)
        if not video_path:
             return jsonify({'error': 'Video download failed.'}), 500

        # 3. Process Transcript and GIFs
        transcript = get_video_transcript(video_id)
        if not transcript:
            os.remove(video_path)
            return jsonify({'error': 'Could not fetch transcript for this video.'}), 400

        segments = find_relevant_segments(transcript, prompt)
        if not segments:
            os.remove(video_path)
            return jsonify({'error': 'No relevant segments found.'}), 400

        gif_urls = []
        for i, segment in enumerate(segments):
            output_filename = os.path.join(GIF_OUTPUT_FOLDER, f"{video_id}_{i}.gif")
            created_gif = create_gif_from_segment(video_path, segment, output_filename)
            if created_gif:
                gif_urls.append(f"{request.host_url}{created_gif.replace(os.sep, '/')}")

        os.remove(video_path)
        return jsonify({'gifs': gif_urls})

    except yt_dlp.utils.DownloadError as e:
        print(f"--- YT-DLP DOWNLOAD ERROR --- : {e}")
        return jsonify({'error': 'This video is unavailable or blocked from being downloaded. Please try a different one.'}), 400
    except Exception as e:
        print(f"--- A GENERIC ERROR OCCURRED ---")
        traceback.print_exc()
        return jsonify({'error': 'A server error occurred. Check logs for details.'}), 500

# Route to serve the generated static GIF files
@app.route('/static/gifs/<filename>')
def serve_gif(filename):
    return send_from_directory(app.config['GIF_OUTPUT_FOLDER'], filename)

if __name__ == '__main__':
    app.run(debug=True, port=5000)
