import os
import cloudinary
import cloudinary.uploader
from io import BytesIO
from flask import Flask, render_template, redirect, url_for, request, flash, jsonify, abort
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from PIL import Image
from dotenv import load_dotenv
from models import db, User, Post, Comment, Message, Notification, Reel

load_dotenv()

# ── Config ──────────────────────────────────────────────
BASE_DIR      = os.path.abspath(os.path.dirname(__file__))
UPLOAD_FOLDER = os.path.join(BASE_DIR, 'static', 'uploads')
ALLOWED_EXT        = {'png', 'jpg', 'jpeg', 'gif', 'webp'}
ALLOWED_VIDEO_EXT  = {'mp4', 'mov', 'webm', 'ogg'}
MAX_IMG_SIZE  = (1080, 1080)

app = Flask(__name__)
app.config['SECRET_KEY']          = os.environ.get('SECRET_KEY', 'dev-secret-change-me')
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URL',
    'sqlite:///' + os.path.join(BASE_DIR, 'lumina.db')).replace('postgres://', 'postgresql://')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['UPLOAD_FOLDER']       = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH']  = 200 * 1024 * 1024  # 200 MB

# Cloudinary (used in production; falls back to local in dev)
cloudinary.config(
    cloud_name = os.environ.get('CLOUDINARY_CLOUD_NAME'),
    api_key    = os.environ.get('CLOUDINARY_API_KEY'),
    api_secret = os.environ.get('CLOUDINARY_API_SECRET'),
)
USE_CLOUDINARY = bool(os.environ.get('CLOUDINARY_CLOUD_NAME'))

db.init_app(app)

login_manager = LoginManager(app)
login_manager.login_view = 'login'
login_manager.login_message = ''

os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# ── Error handlers ───────────────────────────────────────
@app.errorhandler(413)
def too_large(e):
    flash('File is too large. Maximum size is 200MB.', 'error')
    return redirect(request.referrer or url_for('index')), 413


# ── Jinja helper: resolve media URLs (local or Cloudinary) ──
@app.context_processor
def inject_helpers():
    def media_url(path):
        if not path:
            return 'https://ui-avatars.com/api/?background=a855f7&color=fff'
        if path.startswith('http'):
            return path
        return url_for('static', filename=path)
    return dict(media_url=media_url)

# ── Helpers ─────────────────────────────────────────────
def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXT

def allowed_video(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_VIDEO_EXT

def save_image(file, folder='posts', size=MAX_IMG_SIZE):
    if USE_CLOUDINARY:
        img = Image.open(file)
        img.thumbnail(size, Image.LANCZOS)
        buf = BytesIO()
        fmt = img.format or 'JPEG'
        img.save(buf, format=fmt)
        buf.seek(0)
        result = cloudinary.uploader.upload(buf, folder=f'lumina/{folder}',
                                            resource_type='image')
        return result['secure_url']
    # local fallback
    filename = secure_filename(file.filename)
    name, ext = os.path.splitext(filename)
    unique_name = f"{name}_{os.urandom(6).hex()}{ext}"
    dest_dir = os.path.join(UPLOAD_FOLDER, folder)
    os.makedirs(dest_dir, exist_ok=True)
    path = os.path.join(dest_dir, unique_name)
    img = Image.open(file)
    img.thumbnail(size, Image.LANCZOS)
    img.save(path)
    return f"uploads/{folder}/{unique_name}"

def save_video(file):
    if USE_CLOUDINARY:
        result = cloudinary.uploader.upload(file, folder='lumina/reels',
                                            resource_type='video')
        return result['secure_url']
    filename = secure_filename(file.filename)
    name, ext = os.path.splitext(filename)
    unique_name = f"{name}_{os.urandom(6).hex()}{ext}"
    dest_dir = os.path.join(UPLOAD_FOLDER, 'reels')
    os.makedirs(dest_dir, exist_ok=True)
    path = os.path.join(dest_dir, unique_name)
    file.save(path)
    return f"uploads/reels/{unique_name}"

def save_image(file, folder='posts', size=MAX_IMG_SIZE):
    filename = secure_filename(file.filename)
    name, ext = os.path.splitext(filename)
    unique_name = f"{name}_{os.urandom(6).hex()}{ext}"
    dest_dir = os.path.join(UPLOAD_FOLDER, folder)
    os.makedirs(dest_dir, exist_ok=True)
    path = os.path.join(dest_dir, unique_name)
    img = Image.open(file)
    img.thumbnail(size, Image.LANCZOS)
    img.save(path)
    return f"uploads/{folder}/{unique_name}"

def push_notification(user_id, actor_id, kind, post_id=None):
    """Create a notification; skip if actor == recipient."""
    if user_id == actor_id:
        return
    n = Notification(user_id=user_id, actor_id=actor_id, kind=kind, post_id=post_id)
    db.session.add(n)

def extract_yt_id(url):
    """Extract YouTube video ID from any YouTube URL format."""
    import re
    patterns = [
        r'(?:youtube\.com/watch\?v=|youtu\.be/|youtube\.com/shorts/|youtube\.com/embed/)([a-zA-Z0-9_-]{11})',
    ]
    for p in patterns:
        m = re.search(p, url)
        if m:
            # strip any trailing query params that got captured
            return m.group(1)[:11]
    return None

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# ── Auth ─────────────────────────────────────────────────
@app.route('/register', methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated:
        return redirect(url_for('index'))
    if request.method == 'POST':
        username = request.form['username'].strip().lower()
        email    = request.form['email'].strip().lower()
        password = request.form['password']
        if User.query.filter_by(username=username).first():
            flash('Username already taken.', 'error')
        elif User.query.filter_by(email=email).first():
            flash('Email already registered.', 'error')
        elif len(password) < 6:
            flash('Password must be at least 6 characters.', 'error')
        else:
            user = User(username=username, email=email,
                        password=generate_password_hash(password))
            db.session.add(user)
            db.session.commit()
            login_user(user)
            return redirect(url_for('index'))
    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('index'))
    if request.method == 'POST':
        username = request.form['username'].strip().lower()
        password = request.form['password']
        user = User.query.filter_by(username=username).first()
        if user and check_password_hash(user.password, password):
            login_user(user, remember=True)
            return redirect(request.args.get('next') or url_for('index'))
        flash('Invalid username or password.', 'error')
    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))

# ── Feed ─────────────────────────────────────────────────
@app.route('/')
@login_required
def index():
    posts = current_user.feed_posts().all()
    # Suggest users not yet followed
    suggestions = User.query.filter(
        User.id != current_user.id,
        ~User.followers.any(User.id == current_user.id)
    ).order_by(db.func.random()).limit(5).all()
    return render_template('index.html', posts=posts, suggestions=suggestions)

# ── Upload Post ──────────────────────────────────────────
@app.route('/upload', methods=['GET', 'POST'])
@login_required
def upload():
    if request.method == 'POST':
        file    = request.files.get('photo')
        caption = request.form.get('caption', '').strip()
        location = request.form.get('location', '').strip()
        if not file or not allowed_file(file.filename):
            flash('Please upload a valid image (png, jpg, gif, webp).', 'error')
            return redirect(url_for('upload'))
        image_path = save_image(file)
        post = Post(image=image_path, caption=caption, location=location,
                    user_id=current_user.id)
        db.session.add(post)
        db.session.commit()
        flash('Post shared!', 'success')
        return redirect(url_for('index'))
    return render_template('upload.html')

# ── Profile ──────────────────────────────────────────────
@app.route('/profile/<username>')
@login_required
def profile(username):
    user  = User.query.filter_by(username=username).first_or_404()
    posts = Post.query.filter_by(user_id=user.id).order_by(Post.created_at.desc()).all()
    return render_template('profile.html', user=user, posts=posts)

# ── Follow / Unfollow (AJAX) ─────────────────────────────
@app.route('/follow/<int:user_id>', methods=['POST'])
@login_required
def follow(user_id):
    user = User.query.get_or_404(user_id)
    if user == current_user:
        return jsonify({'error': 'Cannot follow yourself'}), 400
    current_user.follow(user)
    push_notification(user.id, current_user.id, 'follow')
    db.session.commit()
    return jsonify({'status': 'following', 'followers': user.followers.count()})

@app.route('/unfollow/<int:user_id>', methods=['POST'])
@login_required
def unfollow(user_id):
    user = User.query.get_or_404(user_id)
    current_user.unfollow(user)
    db.session.commit()
    return jsonify({'status': 'unfollowed', 'followers': user.followers.count()})

# ── Like / Unlike (AJAX) ─────────────────────────────────
@app.route('/like/<int:post_id>', methods=['POST'])
@login_required
def like(post_id):
    post = Post.query.get_or_404(post_id)
    if post.is_liked_by(current_user):
        post.liked_by.remove(current_user)
        liked = False
    else:
        post.liked_by.append(current_user)
        liked = True
        push_notification(post.user_id, current_user.id, 'like', post.id)
    db.session.commit()
    return jsonify({'liked': liked, 'count': post.like_count()})

# ── Comment (AJAX) ───────────────────────────────────────
@app.route('/comment/<int:post_id>', methods=['POST'])
@login_required
def comment(post_id):
    post = Post.query.get_or_404(post_id)
    body = request.json.get('body', '').strip()
    if not body:
        return jsonify({'error': 'Empty comment'}), 400
    c = Comment(body=body, user_id=current_user.id, post_id=post.id)
    db.session.add(c)
    push_notification(post.user_id, current_user.id, 'comment', post.id)
    db.session.commit()
    return jsonify({
        'id': c.id,
        'body': c.body,
        'username': current_user.username,
        'avatar': current_user.avatar
    })

# ── Delete Post ──────────────────────────────────────────
@app.route('/post/<int:post_id>/delete', methods=['POST'])
@login_required
def delete_post(post_id):
    post = Post.query.get_or_404(post_id)
    if post.user_id != current_user.id:
        abort(403)
    # Remove image file
    img_path = os.path.join(BASE_DIR, 'static', post.image)
    if os.path.exists(img_path):
        os.remove(img_path)
    db.session.delete(post)
    db.session.commit()
    return jsonify({'status': 'deleted'})

# ── Edit Profile ────────────────────────────────────────
@app.route('/edit-profile', methods=['GET', 'POST'])
@login_required
def edit_profile():
    if request.method == 'POST':
        username    = request.form.get('username', '').strip().lower()
        bio         = request.form.get('bio', '').strip()
        website     = request.form.get('website', '').strip()
        email       = request.form.get('email', '').strip().lower()
        cur_pw      = request.form.get('current_password', '')
        new_pw      = request.form.get('new_password', '')
        avatar_file = request.files.get('avatar')

        # Username uniqueness check (allow keeping same)
        if username != current_user.username:
            if User.query.filter_by(username=username).first():
                flash('Username already taken.', 'error')
                return redirect(url_for('edit_profile'))

        # Email uniqueness check
        if email != current_user.email:
            if User.query.filter_by(email=email).first():
                flash('Email already in use.', 'error')
                return redirect(url_for('edit_profile'))

        # Password change
        if new_pw:
            if not check_password_hash(current_user.password, cur_pw):
                flash('Current password is incorrect.', 'error')
                return redirect(url_for('edit_profile'))
            if len(new_pw) < 6:
                flash('New password must be at least 6 characters.', 'error')
                return redirect(url_for('edit_profile'))
            current_user.password = generate_password_hash(new_pw)

        # Avatar upload
        if avatar_file and avatar_file.filename and allowed_file(avatar_file.filename):
            # Remove old avatar if not default
            if current_user.avatar != 'default.png':
                old_path = os.path.join(BASE_DIR, 'static', current_user.avatar)
                if os.path.exists(old_path):
                    os.remove(old_path)
            current_user.avatar = save_image(avatar_file, folder='avatars', size=(300, 300))

        current_user.username = username
        current_user.bio      = bio
        current_user.website  = website
        current_user.email    = email
        db.session.commit()
        flash('Profile updated.', 'success')
        return redirect(url_for('profile', username=current_user.username))

    return render_template('edit_profile.html')

# ── Explore ──────────────────────────────────────────────
@app.route('/explore')
@login_required
def explore():
    posts = Post.query.order_by(Post.created_at.desc()).limit(30).all()
    return render_template('explore.html', posts=posts)

# ── Notifications ─────────────────────────────────────────
@app.route('/notifications')
@login_required
def notifications():
    notifs = Notification.query.filter_by(user_id=current_user.id)\
                               .order_by(Notification.created_at.desc()).limit(50).all()
    # Mark all as read
    Notification.query.filter_by(user_id=current_user.id, is_read=False).update({'is_read': True})
    db.session.commit()
    return render_template('notifications.html', notifs=notifs)

@app.route('/notifications/count')
@login_required
def notif_count():
    count = Notification.query.filter_by(user_id=current_user.id, is_read=False).count()
    return jsonify({'count': count})

# ── Messages ──────────────────────────────────────────────
@app.route('/messages')
@login_required
def messages():
    # Get all users this person has a conversation with
    from sqlalchemy import or_
    convos = db.session.query(User).join(
        Message,
        or_(
            (Message.sender_id == User.id) & (Message.receiver_id == current_user.id),
            (Message.receiver_id == User.id) & (Message.sender_id == current_user.id)
        )
    ).filter(User.id != current_user.id).distinct().all()

    # Get unread count per conversation partner
    unread_map = {}
    for u in convos:
        unread_map[u.id] = Message.query.filter_by(
            sender_id=u.id, receiver_id=current_user.id, is_read=False
        ).count()

    # Last message per conversation
    last_msg = {}
    for u in convos:
        msg = Message.query.filter(
            or_(
                (Message.sender_id == current_user.id) & (Message.receiver_id == u.id),
                (Message.sender_id == u.id) & (Message.receiver_id == current_user.id)
            )
        ).order_by(Message.created_at.desc()).first()
        last_msg[u.id] = msg

    # All users for new conversation
    all_users = User.query.filter(User.id != current_user.id).order_by(User.username).all()
    return render_template('messages.html', convos=convos, unread_map=unread_map,
                           last_msg=last_msg, all_users=all_users, active_user=None, thread=[])

@app.route('/messages/<int:user_id>', methods=['GET', 'POST'])
@login_required
def message_thread(user_id):
    from sqlalchemy import or_
    other = User.query.get_or_404(user_id)

    if request.method == 'POST':
        body = request.json.get('body', '').strip()
        if body:
            m = Message(sender_id=current_user.id, receiver_id=user_id, body=body)
            db.session.add(m)
            db.session.commit()
            return jsonify({
                'id': m.id,
                'body': m.body,
                'sender_id': m.sender_id,
                'created_at': m.created_at.strftime('%H:%M')
            })
        return jsonify({'error': 'empty'}), 400

    # Mark incoming as read
    Message.query.filter_by(sender_id=user_id, receiver_id=current_user.id, is_read=False)\
                 .update({'is_read': True})
    db.session.commit()

    thread = Message.query.filter(
        or_(
            (Message.sender_id == current_user.id) & (Message.receiver_id == user_id),
            (Message.sender_id == user_id) & (Message.receiver_id == current_user.id)
        )
    ).order_by(Message.created_at.asc()).all()

    convos = db.session.query(User).join(
        Message,
        or_(
            (Message.sender_id == User.id) & (Message.receiver_id == current_user.id),
            (Message.receiver_id == User.id) & (Message.sender_id == current_user.id)
        )
    ).filter(User.id != current_user.id).distinct().all()

    # ensure the active user appears in convos list
    if other not in convos:
        convos.insert(0, other)

    unread_map = {}
    last_msg = {}
    for u in convos:
        unread_map[u.id] = Message.query.filter_by(
            sender_id=u.id, receiver_id=current_user.id, is_read=False
        ).count()
        msg = Message.query.filter(
            or_(
                (Message.sender_id == current_user.id) & (Message.receiver_id == u.id),
                (Message.sender_id == u.id) & (Message.receiver_id == current_user.id)
            )
        ).order_by(Message.created_at.desc()).first()
        last_msg[u.id] = msg

    all_users = User.query.filter(User.id != current_user.id).order_by(User.username).all()
    return render_template('messages.html', convos=convos, unread_map=unread_map,
                           last_msg=last_msg, all_users=all_users,
                           active_user=other, thread=thread)

@app.route('/messages/poll/<int:user_id>')
@login_required
def message_poll(user_id):
    from sqlalchemy import or_
    after = request.args.get('after', 0, type=int)
    msgs = Message.query.filter(
        or_(
            (Message.sender_id == current_user.id) & (Message.receiver_id == user_id),
            (Message.sender_id == user_id) & (Message.receiver_id == current_user.id)
        ),
        Message.id > after
    ).order_by(Message.created_at.asc()).all()
    # mark incoming as read
    for m in msgs:
        if m.sender_id == user_id:
            m.is_read = True
    db.session.commit()
    return jsonify({'messages': [
        {'id': m.id, 'body': m.body, 'sender_id': m.sender_id,
         'created_at': m.created_at.strftime('%H:%M')} for m in msgs
    ]})

# ── YouTube Shorts API ───────────────────────────────────
def fetch_yt_shorts(query='shorts', max_results=20):
    """Fetch YouTube Shorts via YouTube Data API v3."""
    api_key = os.environ.get('YOUTUBE_API_KEY')
    if not api_key or api_key == 'your_youtube_api_key_here':
        return []
    try:
        from googleapiclient.discovery import build
        youtube = build('youtube', 'v3', developerKey=api_key)
        # Search for shorts (vertical videos under 60s)
        search_resp = youtube.search().list(
            part='snippet',
            q=query + ' #shorts',
            type='video',
            videoDuration='short',
            maxResults=max_results,
            order='viewCount',
            relevanceLanguage='en'
        ).execute()

        video_ids = [item['id']['videoId'] for item in search_resp.get('items', [])]
        if not video_ids:
            return []

        # Get video details to filter actual shorts (≤60s)
        videos_resp = youtube.videos().list(
            part='snippet,contentDetails,statistics',
            id=','.join(video_ids)
        ).execute()

        shorts = []
        for item in videos_resp.get('items', []):
            duration = item['contentDetails']['duration']  # e.g. PT58S
            # Parse ISO 8601 duration — keep only ≤60s
            import re
            m = re.match(r'PT(?:(\d+)M)?(?:(\d+)S)?', duration)
            minutes = int(m.group(1) or 0)
            seconds = int(m.group(2) or 0)
            total   = minutes * 60 + seconds
            if total <= 60:
                shorts.append({
                    'id':        item['id'],
                    'title':     item['snippet']['title'],
                    'channel':   item['snippet']['channelTitle'],
                    'thumb':     item['snippet']['thumbnails'].get('high', {}).get('url', ''),
                    'views':     item['statistics'].get('viewCount', '0'),
                    'likes':     item['statistics'].get('likeCount', '0'),
                })
        return shorts
    except Exception as e:
        print(f'YouTube API error: {e}')
        return []

@app.route('/reels/youtube')
@login_required
def yt_shorts_feed():
    query = request.args.get('q', 'trending')
    shorts = fetch_yt_shorts(query=query, max_results=20)
    return render_template('yt_shorts.html', shorts=shorts, query=query)

@app.route('/reels/youtube/search')
@login_required
def yt_shorts_search():
    query = request.args.get('q', 'trending')
    shorts = fetch_yt_shorts(query=query, max_results=20)
    return jsonify(shorts)

# ── Reels ─────────────────────────────────────────────────
@app.route('/reels')
@login_required
def reels():
    all_reels = Reel.query.order_by(Reel.created_at.desc()).all()
    return render_template('reels.html', reels=all_reels)

@app.route('/reels/upload', methods=['GET', 'POST'])
@login_required
def upload_reel():
    if request.method == 'POST':
        yt_url  = request.form.get('yt_url', '').strip()
        file    = request.files.get('video')
        caption = request.form.get('caption', '').strip()

        if yt_url:
            # Extract YouTube video ID from any YT URL format
            yt_id = extract_yt_id(yt_url)
            if not yt_id:
                flash('Invalid YouTube URL. Please paste a valid YouTube or YouTube Shorts link.', 'error')
                return redirect(url_for('upload_reel'))
            reel = Reel(yt_id=yt_id, caption=caption, user_id=current_user.id)
        elif file and file.filename and allowed_video(file.filename):
            video_path = save_video(file)
            reel = Reel(video=video_path, caption=caption, user_id=current_user.id)
        else:
            flash('Please upload a video file or paste a YouTube URL.', 'error')
            return redirect(url_for('upload_reel'))

        db.session.add(reel)
        db.session.commit()
        flash('Reel shared!', 'success')
        return redirect(url_for('reels'))
    return render_template('upload_reel.html')

@app.route('/reels/like/<int:reel_id>', methods=['POST'])
@login_required
def like_reel(reel_id):
    reel = Reel.query.get_or_404(reel_id)
    if reel.is_liked_by(current_user):
        reel.liked_by.remove(current_user)
        liked = False
    else:
        reel.liked_by.append(current_user)
        liked = True
    db.session.commit()
    return jsonify({'liked': liked, 'count': reel.like_count()})

@app.route('/reels/delete/<int:reel_id>', methods=['POST'])
@login_required
def delete_reel(reel_id):
    reel = Reel.query.get_or_404(reel_id)
    if reel.user_id != current_user.id:
        abort(403)
    vid_path = os.path.join(BASE_DIR, 'static', reel.video)
    if os.path.exists(vid_path):
        os.remove(vid_path)
    db.session.delete(reel)
    db.session.commit()
    return jsonify({'status': 'deleted'})

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    print("✅ Lumina running at http://127.0.0.1:5000")
    print("✅ On your network: http://192.168.0.106:5000")
    print("   Press CTRL+C to stop\n")
    app.run(host='0.0.0.0', port=5000, debug=False)
