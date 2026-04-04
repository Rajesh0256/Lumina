from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from datetime import datetime

db = SQLAlchemy()

# Follow association table
follows = db.Table('follows',
    db.Column('follower_id', db.Integer, db.ForeignKey('user.id'), primary_key=True),
    db.Column('followed_id', db.Integer, db.ForeignKey('user.id'), primary_key=True)
)

# Like association table
likes = db.Table('likes',
    db.Column('user_id', db.Integer, db.ForeignKey('user.id'), primary_key=True),
    db.Column('post_id', db.Integer, db.ForeignKey('post.id'), primary_key=True)
)

class User(UserMixin, db.Model):
    id         = db.Column(db.Integer, primary_key=True)
    username   = db.Column(db.String(40), unique=True, nullable=False)
    email      = db.Column(db.String(120), unique=True, nullable=False)
    password   = db.Column(db.String(256), nullable=False)
    avatar     = db.Column(db.String(256), default='default.png')
    bio        = db.Column(db.String(160), default='')
    website    = db.Column(db.String(120), default='')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    posts = db.relationship('Post', backref='author', lazy='dynamic', cascade='all, delete-orphan')

    following = db.relationship(
        'User', secondary=follows,
        primaryjoin=(follows.c.follower_id == id),
        secondaryjoin=(follows.c.followed_id == id),
        backref=db.backref('followers', lazy='dynamic'),
        lazy='dynamic'
    )

    def follow(self, user):
        if not self.is_following(user):
            self.following.append(user)

    def unfollow(self, user):
        if self.is_following(user):
            self.following.remove(user)

    def is_following(self, user):
        return self.following.filter(follows.c.followed_id == user.id).count() > 0

    def feed_posts(self):
        """Posts from followed users + own posts, newest first."""
        followed = Post.query.join(follows, (follows.c.followed_id == Post.user_id))\
                             .filter(follows.c.follower_id == self.id)
        own = Post.query.filter_by(user_id=self.id)
        return followed.union(own).order_by(Post.created_at.desc())


class Post(db.Model):
    id         = db.Column(db.Integer, primary_key=True)
    image      = db.Column(db.String(256), nullable=False)
    caption    = db.Column(db.String(300), default='')
    location   = db.Column(db.String(100), default='')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    user_id    = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)

    liked_by = db.relationship('User', secondary=likes, backref=db.backref('liked_posts', lazy='dynamic'), lazy='dynamic')

    comments = db.relationship('Comment', backref='post', lazy='dynamic', cascade='all, delete-orphan')

    def like_count(self):
        return self.liked_by.count()

    def is_liked_by(self, user):
        return self.liked_by.filter(likes.c.user_id == user.id).count() > 0


class Comment(db.Model):
    id         = db.Column(db.Integer, primary_key=True)
    body       = db.Column(db.String(300), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    user_id    = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    post_id    = db.Column(db.Integer, db.ForeignKey('post.id'), nullable=False)

    author = db.relationship('User', backref='comments')


class Message(db.Model):
    id          = db.Column(db.Integer, primary_key=True)
    sender_id   = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    receiver_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    body        = db.Column(db.String(1000), nullable=False)
    is_read     = db.Column(db.Boolean, default=False)
    created_at  = db.Column(db.DateTime, default=datetime.utcnow)

    sender   = db.relationship('User', foreign_keys=[sender_id],   backref='sent_messages')
    receiver = db.relationship('User', foreign_keys=[receiver_id], backref='received_messages')


reel_likes = db.Table('reel_likes',
    db.Column('user_id', db.Integer, db.ForeignKey('user.id'), primary_key=True),
    db.Column('reel_id', db.Integer, db.ForeignKey('reel.id'), primary_key=True)
)

class Reel(db.Model):
    id         = db.Column(db.Integer, primary_key=True)
    video      = db.Column(db.String(256), nullable=True)   # local upload
    yt_id      = db.Column(db.String(20),  nullable=True)   # YouTube video ID
    caption    = db.Column(db.String(300), default='')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    user_id    = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)

    author   = db.relationship('User', backref='reels')
    liked_by = db.relationship('User', secondary=reel_likes,
                               backref=db.backref('liked_reels', lazy='dynamic'), lazy='dynamic')

    def like_count(self):
        return self.liked_by.count()

    def is_liked_by(self, user):
        return self.liked_by.filter(reel_likes.c.user_id == user.id).count() > 0

    @property
    def is_youtube(self):
        return bool(self.yt_id)


class Notification(db.Model):
    id         = db.Column(db.Integer, primary_key=True)
    user_id    = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)  # who receives it
    actor_id   = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)  # who triggered it
    kind       = db.Column(db.String(20), nullable=False)  # 'like', 'comment', 'follow'
    post_id    = db.Column(db.Integer, db.ForeignKey('post.id'), nullable=True)
    is_read    = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    user  = db.relationship('User', foreign_keys=[user_id],  backref='notifications')
    actor = db.relationship('User', foreign_keys=[actor_id])
    post  = db.relationship('Post')
