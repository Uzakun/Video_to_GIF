# backend/app.py (Alternative Version - No ImageMagick needed)

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
        print(f"DEBUG: Attempting to get transcript for video ID: {video_id}")
        transcript_list = YouTubeTranscriptApi.list_transcripts(video_id)
        print(f"DEBUG: Available transcripts: {[t.language_code for t in transcript_list]}")
        
        # Try English first, then fall back to any available transcript
        try:
            transcript = transcript_list.find_transcript(['en'])
        except:
            print("DEBUG: English transcript not found, trying any available transcript...")
            transcript = transcript_list.find_transcript([t.language_code for t in transcript_list])
        
        fetched_transcript = transcript.fetch()
        print(f"DEBUG: Successfully fetched transcript with {len(fetched_transcript)} segments")
        return fetched_transcript
    except Exception as e:
        print(f"!!! Could not get transcript. Error: {e}")
        traceback.print_exc()
        return None

def find_relevant_segments(transcript, prompt, count=3):
    print(f"DEBUG: Finding segments for prompt: '{prompt}'")
    print(f"DEBUG: Transcript has {len(transcript)} total segments")
    
    # Filter out common stop words and focus on meaningful keywords
    stop_words = {'the', 'is', 'to', 'and', 'or', 'but', 'in', 'on', 'at', 'by', 'for', 'with', 'about', 'a', 'an', 'of', 'that', 'this', 'it', 'be', 'are', 'was', 'were', 'been', 'have', 'has', 'had', 'do', 'does', 'did', 'will', 'would', 'should', 'could', 'can', 'may', 'might', 'must', 'shall', 'i', 'you', 'he', 'she', 'we', 'they', 'me', 'him', 'her', 'us', 'them'}
    
    prompt_keywords = set(word.lower() for word in prompt.split() if word.lower() not in stop_words and len(word) > 2)
    print(f"DEBUG: Meaningful keywords after filtering: {prompt_keywords}")
    
    scored_segments = []
    
    # Strategy 1: Look for exact and partial keyword matches
    for segment in transcript:
        text = segment.text.lower()
        
        # Score based on exact word matches
        exact_matches = sum(1 for word in prompt_keywords if word in text.split())
        
        # Score based on partial matches (substring matching)
        partial_matches = sum(1 for word in prompt_keywords if word in text)
        
        # Give more weight to exact matches
        total_score = exact_matches * 2 + partial_matches
        
        if total_score > 0:
            print(f"DEBUG: Found matching segment (exact: {exact_matches}, partial: {partial_matches}, total: {total_score}): '{segment.text[:100]}...'")
            scored_segments.append({'segment': segment, 'score': total_score})
    
    print(f"DEBUG: Found {len(scored_segments)} high-quality matching segments")
    
    # Strategy 2: If we don't have enough segments, try broader search with all words
    if len(scored_segments) < count:
        print("DEBUG: Need more segments, trying broader search...")
        all_prompt_words = set(prompt.lower().split())
        # Use start times to check if already added
        used_start_times = {item['segment'].start for item in scored_segments}
        
        for segment in transcript:
            # Skip if already added
            if segment.start in used_start_times:
                continue
                
            text = segment.text.lower()
            score = sum(1 for word in all_prompt_words if word in text)
            if score > 0:
                print(f"DEBUG: Broad search - Found segment (score {score}): '{segment.text[:100]}...'")
                scored_segments.append({'segment': segment, 'score': score})
                used_start_times.add(segment.start)
    
    # Strategy 3: If still not enough, try substring matching
    if len(scored_segments) < count:
        print("DEBUG: Still need more segments, trying substring matching...")
        # Use start times to check if already added
        used_start_times = {item['segment'].start for item in scored_segments}
        
        for segment in transcript:
            # Skip if already added
            if segment.start in used_start_times:
                continue
                
            text = segment.text.lower()
            prompt_lower = prompt.lower()
            # Check if any 3+ character substring of the prompt appears in the text
            for i in range(len(prompt_lower) - 2):
                substring = prompt_lower[i:i+3]
                if substring in text and substring.strip():
                    print(f"DEBUG: Substring match found: '{segment.text[:100]}...'")
                    scored_segments.append({'segment': segment, 'score': 0.5})
                    used_start_times.add(segment.start)
                    break
    
    # Strategy 4: Final fallback - ensure we always have enough segments
    if len(scored_segments) < count:
        print(f"DEBUG: Still only have {len(scored_segments)} segments, adding random segments to reach {count}...")
        # Get segments that haven't been added yet - use start times to identify unique segments
        used_start_times = {item['segment'].start for item in scored_segments}
        available_segments = [seg for seg in transcript if seg.start not in used_start_times]
        
        # Add segments from different parts of the video
        if available_segments:
            # Take segments from beginning, middle, and end
            segment_indices = []
            if len(available_segments) >= 3:
                segment_indices = [
                    0,  # Beginning
                    len(available_segments) // 2,  # Middle
                    len(available_segments) - 1  # End
                ]
            else:
                segment_indices = list(range(len(available_segments)))
            
            for idx in segment_indices:
                if len(scored_segments) >= count:
                    break
                segment = available_segments[idx]
                print(f"DEBUG: Adding fallback segment: '{segment.text[:100]}...'")
                scored_segments.append({'segment': segment, 'score': 0})
    
    # Sort by score and return top segments
    scored_segments.sort(key=lambda x: x['score'], reverse=True)
    result_segments = [item['segment'] for item in scored_segments[:count]]
    
    print(f"DEBUG: Returning {len(result_segments)} segments total")
    return result_segments

def add_text_to_frame(frame, text, position='bottom'):
    """Add text to a frame using PIL (no ImageMagick required)"""
    try:
        # Convert frame from BGR to RGB
        frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        pil_image = Image.fromarray(frame_rgb)
        
        # Create draw object
        draw = ImageDraw.Draw(pil_image)
        
        # Try to use a system font, fall back to default if not available
        try:
            font = ImageFont.truetype("arial.ttf", 20)
        except:
            try:
                font = ImageFont.truetype("C:/Windows/Fonts/arial.ttf", 20)
            except:
                font = ImageFont.load_default()
        
        # Wrap text to fit frame width
        img_width, img_height = pil_image.size
        wrapped_text = textwrap.fill(text, width=int(img_width / 12))
        
        # Calculate text position
        bbox = draw.textbbox((0, 0), wrapped_text, font=font)
        text_width = bbox[2] - bbox[0]
        text_height = bbox[3] - bbox[1]
        
        if position == 'bottom':
            x = (img_width - text_width) // 2
            y = img_height - text_height - 20
        else:
            x = (img_width - text_width) // 2
            y = 20
        
        # Draw text with outline
        outline_range = 2
        for dx in range(-outline_range, outline_range + 1):
            for dy in range(-outline_range, outline_range + 1):
                if dx != 0 or dy != 0:
                    draw.text((x + dx, y + dy), wrapped_text, font=font, fill='black')
        
        # Draw main text
        draw.text((x, y), wrapped_text, font=font, fill='white')
        
        # Convert back to BGR for OpenCV
        frame_with_text = cv2.cvtColor(np.array(pil_image), cv2.COLOR_RGB2BGR)
        return frame_with_text
        
    except Exception as e:
        print(f"DEBUG: Error adding text to frame: {e}")
        return frame

def create_gif_from_segment(video_path, segment, output_filename):
    start_time = segment.start
    duration = segment.duration
    end_time = start_time + min(duration, 5)
    text = segment.text
    
    print(f"DEBUG: Creating GIF for segment: '{text[:50]}...' ({start_time:.1f}s - {end_time:.1f}s)")
    
    try:
        # Extract frames using MoviePy
        with VideoFileClip(video_path).subclip(start_time, end_time) as video_clip:
            # Get frames and add text
            frames_with_text = []
            
            for t in np.arange(0, video_clip.duration, 1/10):  # 10 FPS
                frame = video_clip.get_frame(t)
                # Convert from RGB to BGR for OpenCV
                frame_bgr = cv2.cvtColor(frame, cv2.COLOR_RGB2BGR)
                # Add text
                frame_with_text = add_text_to_frame(frame_bgr, text)
                # Convert back to RGB for GIF
                frame_rgb = cv2.cvtColor(frame_with_text, cv2.COLOR_BGR2RGB)
                frames_with_text.append(frame_rgb)
            
            # Save as GIF using PIL
            if frames_with_text:
                pil_frames = [Image.fromarray(frame) for frame in frames_with_text]
                pil_frames[0].save(
                    output_filename,
                    save_all=True,
                    append_images=pil_frames[1:],
                    duration=100,  # 100ms between frames = 10 FPS
                    loop=0
                )
                print(f"DEBUG: Successfully created GIF with text overlay: {output_filename}")
                return output_filename
            else:
                print("DEBUG: No frames extracted")
                return None
                
    except Exception as e:
        print(f"!!! Error creating GIF: {e}")
        traceback.print_exc()
        return None

# --- Main Route ---

@app.route('/api/generate-gifs', methods=['POST'])
def generate_gifs_route():
    data = request.get_json()
    prompt = data.get('prompt')
    youtube_url = data.get('youtube_url')

    print(f"DEBUG: Received request - Prompt: '{prompt}', URL: '{youtube_url}'")

    if not prompt or not youtube_url:
        print("DEBUG: Missing prompt or YouTube URL")
        return jsonify({'error': 'Prompt and YouTube URL are required.'}), 400

    try:
        # 1. Extract Video Info & ID with yt-dlp
        ydl_opts = {'quiet': True}
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(youtube_url, download=False)
            video_id = info.get('id')
            if not video_id:
                print("DEBUG: Could not extract video ID")
                return jsonify({'error': 'Could not extract video ID from URL.'}), 400

        print(f"DEBUG: Extracted video ID: {video_id}")

        # 2. Download Video using yt-dlp
        video_path_template = os.path.join(TEMP_VIDEO_FOLDER, f"{video_id}.%(ext)s")
        ydl_opts_download = {
            'format': 'best[ext=mp4][height<=480]',
            'outtmpl': video_path_template,
        }
        with yt_dlp.YoutubeDL(ydl_opts_download) as ydl:
            ydl.download([youtube_url])
        
        video_path = video_path_template.replace('.%(ext)s', '.mp4')
        if not os.path.exists(video_path):
             print("DEBUG: Video download failed")
             return jsonify({'error': 'Video download failed.'}), 500

        print(f"DEBUG: Video downloaded to: {video_path}")

        # 3. Get Transcript
        transcript = get_video_transcript(video_id)
        if not transcript:
            print("DEBUG: Could not fetch transcript")
            os.remove(video_path)
            return jsonify({'error': 'Could not fetch transcript for this video.'}), 400

        # 4. Find Relevant Segments
        segments = find_relevant_segments(transcript, prompt, count=3)
        if not segments:
            print("DEBUG: No relevant segments found")
            os.remove(video_path)
            return jsonify({'error': 'No relevant segments found for that prompt.'}), 400

        # 5. Create GIFs
        gif_urls = []
        base_url = request.host_url
        for i, segment in enumerate(segments):
            output_filename = os.path.join(GIF_OUTPUT_FOLDER, f"{video_id}_{i}.gif")
            created_gif_path = create_gif_from_segment(video_path, segment, output_filename)
            if created_gif_path:
                gif_url = f"{base_url}{created_gif_path.replace(os.sep, '/')}"
                gif_urls.append(gif_url)

        os.remove(video_path)
        print(f"DEBUG: Successfully created {len(gif_urls)} GIFs")
        return jsonify({'gifs': gif_urls})

    except Exception as e:
        print("--- A DETAILED ERROR OCCURRED ---")
        traceback.print_exc()
        print("---------------------------------")
        return jsonify({'error': 'A server error occurred. Check the backend terminal for details.'}), 500

# Route to serve the generated static GIF files
@app.route('/static/gifs/<filename>')
def serve_gif(filename):
    return send_from_directory(app.config['GIF_OUTPUT_FOLDER'], filename)

if __name__ == '__main__':
    app.run(debug=True, port=5000)