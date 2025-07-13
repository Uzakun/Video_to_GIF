# backend/app.py

import os
import traceback
import yt_dlp
import cv2
import numpy as np
import whisper
import random
from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
from moviepy.editor import VideoFileClip
from youtube_transcript_api import YouTubeTranscriptApi
from PIL import Image, ImageDraw, ImageFont
import textwrap
import uuid
from sentence_transformers import SentenceTransformer
from sklearn.metrics.pairwise import cosine_similarity

app = Flask(__name__)
CORS(app)

# --- Configuration ---
TEMP_VIDEO_FOLDER = 'temp_videos'
GIF_OUTPUT_FOLDER = 'static/gifs'
app.config['UPLOAD_FOLDER'] = TEMP_VIDEO_FOLDER

# --- Load Models ---
print("Loading Whisper model...")
whisper_model = whisper.load_model("base")
print("Whisper model loaded.")

print("Loading Sentence Transformer model...")
sentence_model = SentenceTransformer('all-MiniLM-L6-v2')
print("Sentence Transformer model loaded.")

# --- Ensure Folders Exist ---
if not os.path.exists(TEMP_VIDEO_FOLDER):
    os.makedirs(TEMP_VIDEO_FOLDER)
if not os.path.exists(GIF_OUTPUT_FOLDER):
    os.makedirs(GIF_OUTPUT_FOLDER)

# --- Helper Functions ---

def get_existing_transcript(video_id):
    try:
        transcript_list = YouTubeTranscriptApi.list_transcripts(video_id)
        transcript = transcript_list.find_transcript(['en'])
        return transcript.fetch()
    except Exception:
        return None

def generate_transcript_with_whisper(video_path):
    try:
        print("Generating transcript with Whisper...")
        result = whisper_model.transcribe(video_path)
        print("Whisper transcription complete.")
        formatted_transcript = []
        for segment in result["segments"]:
            formatted_transcript.append({
                'text': segment['text'],
                'start': segment['start'],
                'duration': segment['end'] - segment['start']
            })
        return formatted_transcript
    except Exception as e:
        print(f"!!! Whisper transcription failed: {e}")
        return None

def find_relevant_segments(transcript, prompt, count=3):
    """
    UPDATED: Ensures variety by creating a larger pool of candidates before randomizing.
    """
    try:
        print("Performing local smart search...")
        segment_texts = [s['text'] if isinstance(s, dict) else s.text for s in transcript]
        
        prompt_embedding = sentence_model.encode([prompt])
        segment_embeddings = sentence_model.encode(segment_texts)
        
        similarities = cosine_similarity(prompt_embedding, segment_embeddings)[0]
        
        # Pair each segment with its similarity score
        scored_segments = []
        for i, segment in enumerate(transcript):
            scored_segments.append({'segment': segment, 'score': similarities[i]})
        
        # Sort by the highest similarity score
        scored_segments.sort(key=lambda x: x['score'], reverse=True)
        
        # Create a pool of the top 20 most relevant segments (or fewer if video is short)
        # This gives us a large enough set to ensure random results.
        candidate_pool = [s['segment'] for s in scored_segments[:20]]
        
        if not candidate_pool:
            print("Smart search found no matches, falling back to random segments.")
            return random.sample(transcript, min(len(transcript), count))

        print(f"Found {len(candidate_pool)} potential segments. Randomly selecting {count}.")
        # Randomly select 'count' segments from the candidate pool for variety
        return random.sample(candidate_pool, min(len(candidate_pool), count))

    except Exception as e:
        print(f"!!! Local smart search failed: {e}. Falling back to random segments.")
        return random.sample(transcript, min(len(transcript), count))


def add_text_to_frame(frame, text):
    try:
        pil_image = Image.fromarray(frame)
        draw = ImageDraw.Draw(pil_image)
        font_size = 48
        try:
            font = ImageFont.truetype("arialbd.ttf", font_size)
        except IOError:
            try:
                font = ImageFont.truetype("arial.ttf", font_size)
            except IOError:
                font = ImageFont.load_default()

        img_width, img_height = pil_image.size
        wrapped_text = textwrap.fill(text, width=int(img_width / 22))

        bbox = draw.textbbox((0, 0), wrapped_text, font=font)
        text_width, text_height = bbox[2] - bbox[0], bbox[3] - bbox[1]
        x, y = (img_width - text_width) / 2, img_height - text_height - 40

        outline_range = 3
        for dx in range(-outline_range, outline_range + 1):
            for dy in range(-outline_range, outline_range + 1):
                if dx != 0 or dy != 0:
                    draw.text((x + dx, y + dy), wrapped_text, font=font, fill="black")

        draw.text((x, y), wrapped_text, font=font, fill="white")
        return np.array(pil_image)
    except Exception as e:
        print(f"!!! Error adding text to frame: {e}")
        return frame

def create_gif_from_segment(video_path, segment, output_filename):
    if isinstance(segment, dict):
        start_time, duration, text = segment['start'], segment['duration'], segment['text']
    else:
        start_time, duration, text = segment.start, segment.duration, segment.text

    end_time = start_time + min(duration, 5)
    
    try:
        with VideoFileClip(video_path).subclip(start_time, end_time) as video_clip:
            frames = [add_text_to_frame(video_clip.get_frame(t), text) for t in np.arange(0, video_clip.duration, 1/10)]
            if frames:
                pil_frames = [Image.fromarray(f) for f in frames]
                pil_frames[0].save(output_filename, save_all=True, append_images=pil_frames[1:], duration=100, loop=0)
                return output_filename
        return None
    except Exception:
        traceback.print_exc()
        return None

# --- Reusable GIF Generation Logic ---
def process_video_and_generate_gifs(video_path, prompt, video_id):
    transcript = get_existing_transcript(video_id) if video_id else None
    if not transcript:
        transcript = generate_transcript_with_whisper(video_path)

    if not transcript:
        if os.path.exists(video_path): os.remove(video_path)
        return None, "Could not get or generate a transcript for this video."

    segments = find_relevant_segments(transcript, prompt, count=3)
    if not segments:
        if os.path.exists(video_path): os.remove(video_path)
        return None, "No relevant segments found for that prompt."

    gif_paths = []
    output_prefix = video_id if video_id else f"upload_{uuid.uuid4().hex}"
    for i, segment in enumerate(segments):
        output_filename = os.path.join(GIF_OUTPUT_FOLDER, f"{output_prefix}_{i}.gif")
        gif_path = create_gif_from_segment(video_path, segment, output_filename)
        if gif_path:
            gif_paths.append(gif_path)
            
    if os.path.exists(video_path): os.remove(video_path)
    return gif_paths, None

# --- Main Routes ---
@app.route('/api/generate-gifs', methods=['POST'])
def generate_gifs_route():
    data = request.get_json()
    prompt, youtube_url = data.get('prompt'), data.get('youtube_url')
    if not prompt or not youtube_url:
        return jsonify({'error': 'Prompt and YouTube URL are required.'}), 400
    try:
        with yt_dlp.YoutubeDL({'quiet': True}) as ydl:
            info = ydl.extract_info(youtube_url, download=False)
            video_id = info.get('id')
        
        video_path_template = os.path.join(TEMP_VIDEO_FOLDER, f"{video_id}.%(ext)s")
        with yt_dlp.YoutubeDL({'format': 'best[ext=mp4][height<=480]', 'outtmpl': video_path_template}) as ydl:
            ydl.download([youtube_url])
        
        video_path = video_path_template.replace('.%(ext)s', '.mp4')
        
        gif_paths, error = process_video_and_generate_gifs(video_path, prompt, video_id)
        if error:
            return jsonify({'error': error}), 400
            
        base_url = request.host_url
        gif_urls = [f"{base_url}static/gifs/{os.path.basename(path)}" for path in gif_paths]
        return jsonify({'gifs': gif_urls})
    except Exception:
        traceback.print_exc()
        return jsonify({'error': 'A server error occurred.'}), 500

@app.route('/api/generate-gifs-from-upload', methods=['POST'])
def generate_gifs_from_upload_route():
    if 'video' not in request.files:
        return jsonify({'error': 'No video file part'}), 400
    
    file, prompt = request.files['video'], request.form.get('prompt')
    if file.filename == '' or not prompt:
        return jsonify({'error': 'No selected file or no prompt provided'}), 400

    if file:
        filename = f"upload_{uuid.uuid4().hex}.mp4"
        video_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        file.save(video_path)
        
        gif_paths, error = process_video_and_generate_gifs(video_path, prompt, video_id=None)
        if error:
            return jsonify({'error': error}), 400
            
        base_url = request.host_url
        gif_urls = [f"{base_url}static/gifs/{os.path.basename(path)}" for path in gif_paths]
        return jsonify({'gifs': gif_urls})

    return jsonify({'error': 'An unknown error occurred during upload.'}), 500

@app.route('/static/gifs/<filename>')
def serve_gif(filename):
    return send_from_directory(GIF_OUTPUT_FOLDER, filename)

if __name__ == '__main__':
    app.run(debug=True, port=5000)
