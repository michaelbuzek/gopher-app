from flask import Flask, render_template, request, jsonify, redirect, url_for
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from sqlalchemy import text
import json
import os
import logging
import glob
from datetime import datetime
from dotenv import load_dotenv

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()
app = Flask(__name__)

# ------------------------------
# Database Configuration (Render-optimized)
# ------------------------------

def get_database_url():
    """Get database URL with proper PostgreSQL handling for Render"""
    database_url = os.environ.get('DATABASE_URL')
    
    if database_url:
        # Render uses postgres:// but SQLAlchemy needs postgresql://
        if database_url.startswith('postgres://'):
            database_url = database_url.replace('postgres://', 'postgresql://', 1)
        logger.info("🐘 Using PostgreSQL (Render)")
        return database_url
    else:
        # Local development
        local_db_path = os.path.join(os.path.dirname(__file__), 'gopher.db')
        logger.info(f"🗄️ Using SQLite (Local): {local_db_path}")
        return f'sqlite:///{local_db_path}'

app.config['SQLALCHEMY_DATABASE_URI'] = get_database_url()
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {
    'pool_pre_ping': True,  # Handle database disconnections
    'pool_recycle': 300,    # Recycle connections every 5 minutes
    'pool_timeout': 20,     # Render.com optimization
    'max_overflow': 0,      # Render.com optimization
}

# Secret key for sessions
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'gopher-dev-key-12345')

db = SQLAlchemy(app)
migrate = Migrate(app, db)

# ------------------------------
# Environment Helper Functions
# ------------------------------

def get_environment():
    """Get current environment with fallback"""
    return os.environ.get('ENVIRONMENT', 'development').lower()

def is_development():
    """Check if we're in development environment"""
    return get_environment() == 'development'

def is_production():
    """Check if we're in production environment"""
    return get_environment() == 'production'

def log_action(action, details=""):
    """Centralized logging with environment awareness"""
    env_prefix = "🔧 DEV" if is_development() else "🛡️ PROD"
    logger.info(f"{env_prefix}: {action} {details}")

# ------------------------------
# Database Models
# ------------------------------

class Place(db.Model):
    """Minigolf-Plätze mit track configuration"""
    __tablename__ = 'places'
    
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False, unique=True)
    track_count = db.Column(db.Integer, nullable=False, default=18)
    is_default = db.Column(db.Boolean, default=False)  # Für "Bülach" Standard
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Relationships
    games = db.relationship('Game', backref='place_config', lazy=True)
    place_tracks = db.relationship('PlaceTrack', backref='place', cascade="all, delete-orphan", lazy=True)
    
    def __repr__(self):
        return f'<Place {self.id}: {self.name} ({self.track_count} tracks)>'
    
    def get_track_config(self):
        """Returns dict {track_number: track_type} für diesen Platz"""
        config = {}
        for pt in self.place_tracks:
            config[pt.track_number] = pt.track_type
        return config
    
    def setup_default_tracks(self):
        """Creates default track configuration für neuen Platz"""
        # Standard Track Type (wenn noch keine spezifische config)
        default_track_type = TrackType.query.filter_by(is_default=True).first()
        if not default_track_type:
            # Fallback: ersten verfügbaren Track Type nehmen
            default_track_type = TrackType.query.first()
        
        if default_track_type:
            for track_num in range(1, self.track_count + 1):
                # Nur erstellen wenn noch nicht existiert
                existing = PlaceTrack.query.filter_by(place=self, track_number=track_num).first()
                if not existing:
                    place_track = PlaceTrack(
                        place=self, 
                        track_number=track_num, 
                        track_type=default_track_type
                    )
                    db.session.add(place_track)


class TrackType(db.Model):
    """Bibliothek von Bahn-Typen (Standard Icons)"""
    __tablename__ = 'track_types'
    
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), nullable=False, unique=True)
    description = db.Column(db.String(200))
    icon_filename = db.Column(db.String(100), nullable=False)  # z.B. "bahn_1.png"
    is_default = db.Column(db.Boolean, default=False)  # Standard Track Type
    is_placeholder = db.Column(db.Boolean, default=False)  # Platzhalter für unbekannte
    sort_order = db.Column(db.Integer, default=0)  # Reihenfolge in Dropdown
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Relationships
    place_tracks = db.relationship('PlaceTrack', backref='track_type', lazy=True)
    
    def __repr__(self):
        return f'<TrackType {self.id}: {self.name}>'
    
    @property
    def icon_url(self):
        """Returns full path to icon"""
        return f'/static/track-icons/{self.icon_filename}'


class PlaceTrack(db.Model):
    """Association Table: Welcher Track-Type für welche Bahn an welchem Platz"""
    __tablename__ = 'place_tracks'
    
    id = db.Column(db.Integer, primary_key=True)
    place_id = db.Column(db.Integer, db.ForeignKey('places.id'), nullable=False)
    track_number = db.Column(db.Integer, nullable=False)  # Bahn 1, 2, 3, etc.
    track_type_id = db.Column(db.Integer, db.ForeignKey('track_types.id'), nullable=False)
    
    # Composite index für Performance & Eindeutigkeit
    __table_args__ = (
        db.Index('idx_place_track_number', 'place_id', 'track_number'),
        db.UniqueConstraint('place_id', 'track_number', name='uq_place_track_number')
    )
    
    def __repr__(self):
        return f'<PlaceTrack {self.place.name} Track {self.track_number}: {self.track_type.name}>'


class Game(db.Model):
    __tablename__ = 'games'
    
    id = db.Column(db.Integer, primary_key=True)
    date = db.Column(db.String(20), nullable=False)
    place = db.Column(db.String(100), nullable=False)  # BEHALTEN für Legacy Games
    place_id = db.Column(db.Integer, db.ForeignKey('places.id'), nullable=True)  # NEU: Referenz zu Place
    track_count = db.Column(db.Integer, nullable=False, default=18)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Relationships
    players = db.relationship('Player', backref='game', cascade="all, delete-orphan", lazy=True)
    
    def __repr__(self):
        return f'<Game {self.id}: {self.place} on {self.date}>'
    
    def get_place_name(self):
        """Returns place name - from Place config or legacy text"""
        if self.place_config:
            return self.place_config.name
        return self.place
    
    def get_track_config(self):
        """Returns track configuration für diese Game"""
        if self.place_config:
            return self.place_config.get_track_config()
        return {}  # Legacy games haben keine track config


class Player(db.Model):
    __tablename__ = 'players'
    
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    game_id = db.Column(db.Integer, db.ForeignKey('games.id'), nullable=False)
    
    # Relationships
    scores = db.relationship('Score', backref='player', cascade="all, delete-orphan", lazy=True)
    
    def __repr__(self):
        return f'<Player {self.id}: {self.name}>'
    
    def get_total_score(self):
        """Calculate total score for this player"""
        return sum(score.value for score in self.scores)

class Score(db.Model):
    __tablename__ = 'scores'
    
    id = db.Column(db.Integer, primary_key=True)
    track = db.Column(db.Integer, nullable=False)
    value = db.Column(db.Integer, nullable=False, default=0)
    player_id = db.Column(db.Integer, db.ForeignKey('players.id'), nullable=False)
    
    # Composite index for performance
    __table_args__ = (db.Index('idx_player_track', 'player_id', 'track'),)
    
    def __repr__(self):
        return f'<Score {self.id}: Track {self.track} = {self.value}>'


# ------------------------------
# Scrabble Models
# ------------------------------

class ScrabbleGame(db.Model):
    """Scrabble Spiel-Historie"""
    __tablename__ = 'scrabble_games'
    
    id = db.Column(db.Integer, primary_key=True)
    date = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    
    # Spieler 1
    player1_name = db.Column(db.String(100), nullable=False)
    player1_total = db.Column(db.Integer, nullable=False, default=0)
    player1_rounds = db.Column(db.Integer, nullable=False, default=0)
    
    # Spieler 2
    player2_name = db.Column(db.String(100), nullable=False)
    player2_total = db.Column(db.Integer, nullable=False, default=0)
    player2_rounds = db.Column(db.Integer, nullable=False, default=0)
    
    # Ergebnis
    winner_name = db.Column(db.String(100), nullable=True)  # null bei Tie
    is_tie = db.Column(db.Boolean, default=False)
    
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    def __repr__(self):
        return f'<ScrabbleGame {self.id}: {self.player1_name} vs {self.player2_name}>'
    
    def to_dict(self):
        return {
            'id': self.id,
            'date': self.date.isoformat(),
            'player1': {
                'name': self.player1_name,
                'total': self.player1_total,
                'moves': self.player1_rounds
            },
            'player2': {
                'name': self.player2_name,
                'total': self.player2_total,
                'moves': self.player2_rounds
            },
            'winner': self.winner_name,
            'isTie': self.is_tie
        }


# ------------------------------
# Ball Notes Models (Feature: persönliche Ball-Wahl pro Spieler/Anlage/Bahn)
# ------------------------------

class PlayerBall(db.Model):
    """Ball aus dem Inventar eines Spielers (z.B. Lumpas 'hellblau')."""
    __tablename__ = 'player_balls'

    id = db.Column(db.Integer, primary_key=True)
    player_name = db.Column(db.String(100), nullable=False)
    label = db.Column(db.String(100), nullable=False)
    color_hex = db.Column(db.String(9), nullable=True)
    image_filename = db.Column(db.String(200), nullable=True)  # Legacy (Dateipfad)
    image_data = db.Column(db.Text, nullable=True)  # Foto als kompaktes data:-URL (Render-sicher, DB-persistiert)
    description = db.Column(db.Text, nullable=True)  # freie Beschreibung (z.B. "hart, springt gut")
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    __table_args__ = (
        db.UniqueConstraint('player_name', 'label', name='uq_player_ball_label'),
        db.Index('idx_player_ball_player', 'player_name'),
    )

    def to_dict(self):
        return {
            'id': self.id,
            'player_name': self.player_name,
            'label': self.label,
            'color_hex': self.color_hex,
            'image_filename': self.image_filename,
            'image_data': self.image_data,
            'description': self.description,
        }


class PlayerTrackChoice(db.Model):
    """Append-only Historie der Ball-/Notiz-Wahl pro (Anlage, Bahn, Spieler).

    Aktuelle Wahl = jüngster Eintrag pro (place_id, track_number, player_name).
    Ältere Einträge bilden die Historie.
    """
    __tablename__ = 'player_track_choices'

    id = db.Column(db.Integer, primary_key=True)
    place_id = db.Column(db.Integer, db.ForeignKey('places.id'), nullable=False)
    track_number = db.Column(db.Integer, nullable=False)
    player_name = db.Column(db.String(100), nullable=False)
    ball_id = db.Column(db.Integer, db.ForeignKey('player_balls.id'), nullable=True)
    note = db.Column(db.Text, nullable=True)
    slot = db.Column(db.Integer, nullable=False, default=0, server_default='0')  # 0 = Haupt-Ball, 1 = Alternativ-Ball
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    ball = db.relationship('PlayerBall', lazy='joined')

    __table_args__ = (
        db.Index('idx_choice_lookup', 'place_id', 'track_number', 'player_name', 'created_at'),
    )

    def to_dict(self):
        return {
            'id': self.id,
            'place_id': self.place_id,
            'track_number': self.track_number,
            'player_name': self.player_name,
            'ball': self.ball.to_dict() if self.ball else None,
            'note': self.note,
            'slot': self.slot if self.slot is not None else 0,
            'created_at': self.created_at.isoformat() if self.created_at else None,
        }


# ------------------------------
# Profile (kanonische Spieler-Identität — "MEIN STUFF")
# ------------------------------

class Profile(db.Model):
    """Feste Spieler-Profile als stabile Identität (kein Login)."""
    __tablename__ = 'profiles'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False, unique=True)  # kanonisch, z.B. 'Umpa'
    color_hex = db.Column(db.String(9), nullable=True)
    image_filename = db.Column(db.String(200), nullable=True)  # Avatar/Foto
    sort_order = db.Column(db.Integer, default=0)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            'id': self.id,
            'name': self.name,
            'color_hex': self.color_hex,
            'image_filename': self.image_filename,
            'sort_order': self.sort_order,
        }


# ------------------------------
# Database Management & Health Check
# ------------------------------

def check_database_connection():
    """Test database connection"""
    try:
        db.session.execute(text('SELECT 1'))
        db.session.commit()  # Commit nach erfolgreicher Query
        return True
    except Exception as e:
        db.session.rollback()  # Rollback bei Fehler
        logger.error(f"❌ Database connection failed: {str(e)}")
        return False

def check_tables_exist():
    """Check if all required tables exist"""
    try:
        # Try to query each table
        db.session.execute(text('SELECT 1 FROM games LIMIT 1'))
        db.session.execute(text('SELECT 1 FROM players LIMIT 1'))
        db.session.execute(text('SELECT 1 FROM scores LIMIT 1'))
        db.session.execute(text('SELECT 1 FROM places LIMIT 1'))
        db.session.execute(text('SELECT 1 FROM track_types LIMIT 1'))
        db.session.execute(text('SELECT 1 FROM place_tracks LIMIT 1'))
        db.session.execute(text('SELECT 1 FROM scrabble_games LIMIT 1'))  # Scrabble Table
        db.session.execute(text('SELECT 1 FROM player_balls LIMIT 1'))  # Ball-Notes Feature
        db.session.execute(text('SELECT 1 FROM player_track_choices LIMIT 1'))  # Ball-Notes Feature
        db.session.commit()  # Commit nach erfolgreichen Queries
        return True
    except Exception:
        db.session.rollback()  # Rollback bei Fehler
        return False

def initialize_default_data():
    """Setup default Track Types - UPDATED VERSION WITH CORRECT ICONS"""
    try:
        # Track Types mit deinen tatsächlichen PNG-Dateien
        default_track_types = [
            {'name': 'Standard', 'description': 'Standard Minigolf Bahn', 'icon_filename': 'bahn_placeholder.png', 'is_default': True, 'sort_order': 1},
            {'name': 'Kurve Links', 'description': 'Linkskurve', 'icon_filename': 'bahn_kurve_links.png', 'sort_order': 2},
            {'name': 'Kurve Rechts', 'description': 'Rechtskurve', 'icon_filename': 'bahn_kurve_rechts.png', 'sort_order': 3},
            {'name': 'Hindernis', 'description': 'Bahn mit Hindernis', 'icon_filename': 'bahn_hindernis.png', 'sort_order': 4},
            {'name': 'Gerade', 'description': 'Gerade Bahn', 'icon_filename': 'gerade.png', 'sort_order': 5},
            {'name': 'Berg', 'description': 'Berg-Bahn', 'icon_filename': 'berg.png', 'sort_order': 6},
            {'name': 'Loop', 'description': 'Loop-Bahn', 'icon_filename': 'loop.png', 'sort_order': 7},
            {'name': 'Rampe', 'description': 'Rampen-Bahn', 'icon_filename': 'rampe.png', 'sort_order': 8},
            {'name': 'Tunnel', 'description': 'Tunnel-Bahn', 'icon_filename': 'tunnel.png', 'sort_order': 9},
            {'name': 'S-Kurve', 'description': 'S-Kurven-Bahn', 'icon_filename': 's_kurve.png', 'sort_order': 10},
            {'name': 'Rechtskurve Alt', 'description': 'Alternative Rechtskurve', 'icon_filename': 'rechtskurve.png', 'sort_order': 11},
            {'name': 'Linkskurve Alt', 'description': 'Alternative Linkskurve', 'icon_filename': 'linkskurve.png', 'sort_order': 12},
            {'name': 'Hindernis Alt', 'description': 'Alternative Hindernis-Bahn', 'icon_filename': 'hindernis.png', 'sort_order': 13},
        ]
        
        for tt_data in default_track_types:
            existing = TrackType.query.filter_by(name=tt_data['name']).first()
            if not existing:
                track_type = TrackType(**tt_data)
                db.session.add(track_type)
        
        db.session.commit()
        log_action("Track Types initialized with correct PNG files")
        
    except Exception as e:
        db.session.rollback()  # Rollback bei Fehler
        logger.error(f"❌ Error initializing default data: {str(e)}")
        raise  # Re-raise damit safe_database_init() es mitbekommt


def migrate_legacy_games():
    """Convert legacy games to use Place references"""
    try:
        legacy_games = Game.query.filter(Game.place_id == None).all()
        
        for game in legacy_games:
            # Versuche existing Place zu finden
            existing_place = Place.query.filter_by(name=game.place).first()
            
            if not existing_place:
                # Erstelle neuen Place für diesen legacy game
                new_place = Place(name=game.place, track_count=game.track_count)
                db.session.add(new_place)
                db.session.flush()  # Get ID
                new_place.setup_default_tracks()
                game.place_id = new_place.id
            else:
                game.place_id = existing_place.id
        
        db.session.commit()
        log_action(f"Migrated {len(legacy_games)} legacy games to Place references")
        
    except Exception as e:
        db.session.rollback()  # Rollback bei Fehler
        logger.error(f"❌ Error migrating legacy games: {str(e)}")
        raise  # Re-raise damit safe_database_init() es mitbekommt


def ensure_schema_additions():
    """Additive, idempotente Schema-Ergänzungen ohne Alembic.
    NUR neue Spalten/Tabellen, niemals destruktiv (siehe DB-Schutzregel)."""
    try:
        if db.engine.dialect.name == 'postgresql':
            db.session.execute(text(
                "ALTER TABLE player_track_choices "
                "ADD COLUMN IF NOT EXISTS slot INTEGER NOT NULL DEFAULT 0"
            ))
            db.session.execute(text(
                "ALTER TABLE player_balls ADD COLUMN IF NOT EXISTS image_data TEXT"
            ))
            db.session.execute(text(
                "ALTER TABLE player_balls ADD COLUMN IF NOT EXISTS description TEXT"
            ))
            db.session.commit()
            log_action("Schema-Ergänzung geprüft: slot, player_balls.image_data, player_balls.description")
    except Exception as e:
        db.session.rollback()
        logger.warning(f"⚠️ ensure_schema_additions übersprungen: {e}")


def ensure_profiles():
    """Additiv: 'profiles'-Tabelle anlegen/seeden + bekannte Namensvarianten
    in players kanonisieren. Idempotent, keine Löschungen (DB-Schutzregel)."""
    canonical = [
        {'name': 'Umpa', 'color_hex': '#16a34a', 'sort_order': 1},
        {'name': 'Lumpa', 'color_hex': '#e0672e', 'sort_order': 2},
    ]
    try:
        db.create_all()  # legt fehlende Tabellen an (z.B. profiles) — additiv
        for p in canonical:
            if not Profile.query.filter_by(name=p['name']).first():
                db.session.add(Profile(**p))
        db.session.commit()
        # Casing-Varianten der bekannten Profile in players angleichen (idempotent)
        for name in ('Umpa', 'Lumpa'):
            db.session.execute(text(
                "UPDATE players SET name = :canon "
                "WHERE lower(name) = lower(:canon) AND name <> :canon"
            ), {'canon': name})
        db.session.commit()
        log_action("Profile geseedet + Spielernamen normalisiert")
    except Exception as e:
        db.session.rollback()
        logger.warning(f"⚠️ ensure_profiles übersprungen: {e}")


def safe_database_init():
    """Updated database initialization"""
    try:
        # Erst rollback um sauberen Zustand zu haben
        db.session.rollback()
        
        # Test connection
        db.session.execute(text('SELECT 1'))
        db.session.commit()
        log_action("Database connection successful")
        
        # Create all tables (including new ones)
        log_action("Creating database tables on startup")
        db.create_all()

        # Additive, idempotente Schema-Ergänzungen (kein Alembic)
        ensure_schema_additions()
        ensure_profiles()

        # Initialize default data
        initialize_default_data()
        
        # Migrate legacy games (if any)
        migrate_legacy_games()
        
        log_action("Database tables and default data initialized successfully")
        return True
        
    except Exception as e:
        db.session.rollback()  # Rollback bei Fehler
        logger.error(f"❌ Database initialization failed: {str(e)}")
        return False

# ------------------------------
# AUTOMATIC DATABASE INITIALIZATION
# ------------------------------

@app.before_request
def ensure_database():
    """Automatically ensure database tables exist before each request"""
    # Skip for static files and health checks
    if request.endpoint in ['static', 'health_check']:
        return
    
    # Only check once per app instance
    if not hasattr(app, '_database_checked'):
        try:
            log_action("Checking database tables...")
            
            if check_database_connection():
                if not check_tables_exist():
                    log_action("Tables missing - creating automatically")
                    success = safe_database_init()
                    if success:
                        log_action("✅ Database auto-initialization successful")
                    else:
                        logger.error("❌ Database auto-initialization failed")
                else:
                    log_action("✅ Database tables verified")
                    ensure_schema_additions()
                    ensure_profiles()

                app._database_checked = True
            else:
                logger.error("❌ Database connection failed during auto-check")
                
        except Exception as e:
            logger.error(f"❌ Database auto-check error: {str(e)}")

# ------------------------------
# Health Check & Manual Init Routes
# ------------------------------

@app.route('/health')
def health_check():
    """Health check endpoint for Render"""
    try:
        # Check database connection
        db_status = check_database_connection()
        tables_exist = check_tables_exist() if db_status else False
        
        # Get basic stats
        game_count = Game.query.count() if db_status and tables_exist else 0
        place_count = Place.query.count() if db_status and tables_exist else 0
        
        status = {
            'status': 'healthy' if (db_status and tables_exist) else 'unhealthy',
            'environment': get_environment(),
            'database': 'connected' if db_status else 'disconnected',
            'tables': 'exist' if tables_exist else 'missing',
            'games_count': game_count,
            'places_count': place_count,
            'auto_init': 'enabled',
            'timestamp': datetime.utcnow().isoformat()
        }
        
        return jsonify(status), 200 if (db_status and tables_exist) else 503
      
    except Exception as e:
        logger.error(f"❌ Health check failed: {str(e)}")
        return jsonify({'status': 'error', 'message': str(e)}), 500

@app.route('/initdb')
def initdb():
    """Manual database initialization - now mostly for debugging"""
    try:
        if is_development():
            # Development: Allow optional reset
            reset_requested = request.args.get('reset', '').lower() == 'true'
            
            if reset_requested:
                log_action("Manual database reset (development only)")
            #    db.drop_all()
                
            success = safe_database_init()
            
            if success:
                action = "reset and created" if reset_requested else "initialized"
                log_action(f"Manual database {action}")
                return f"✅ Development: Database {action} successfully.<br><small>Note: Auto-initialization is now enabled!</small>"
            else:
                return "❌ Database initialization failed.", 500
                
        else:
            # Production: Only safe initialization
            success = safe_database_init()
            
            if success:
                log_action("Manual database initialization")
                return "✅ Production: Database safely initialized.<br><small>Note: This should happen automatically now!</small>"
            else:
                return "❌ Database initialization failed.", 500
                
    except Exception as e:
        logger.error(f"❌ Manual database init error: {str(e)}")
        return f"<h1>Database Error</h1><p>{str(e)}</p>", 500

@app.route('/reset-dev-db')
def reset_dev_db():
    """Development only: Force reset database"""
    if is_production():
        log_action("Unauthorized reset attempt blocked")
        return jsonify({'error': 'Only available in development environment'}), 403
    
    try:
        log_action("Performing complete database reset")
#        db.drop_all()
        success = safe_database_init()
        
        # Reset the check flag so auto-init runs again
        if hasattr(app, '_database_checked'):
            delattr(app, '_database_checked')
        
        if success:
            log_action("Database reset completed")
            return "✅ Development: Database completely reset."
        else:
            return "❌ Database reset failed.", 500
            
    except Exception as e:
        logger.error(f"❌ Reset error: {str(e)}")
        return f"<h1>Reset Error</h1><p>{str(e)}</p>", 500

# 🔥 NEW: Force Reset Track Types für Production (Render.com)
@app.route('/force-reset-track-types')
def force_reset_track_types():
    """Force reset only TrackTypes - safe for production"""
    try:
        log_action("Force resetting TrackTypes only")
        
        # Delete existing track types
        TrackType.query.delete()
        
        # Re-create with updated icon filenames (deine tatsächlichen PNG-Dateien)
        default_track_types = [
            {'name': 'Standard', 'description': 'Standard Minigolf Bahn', 'icon_filename': 'bahn_placeholder.png', 'is_default': True, 'sort_order': 1},
            {'name': 'Kurve Links', 'description': 'Linkskurve', 'icon_filename': 'bahn_kurve_links.png', 'sort_order': 2},
            {'name': 'Kurve Rechts', 'description': 'Rechtskurve', 'icon_filename': 'bahn_kurve_rechts.png', 'sort_order': 3},
            {'name': 'Hindernis', 'description': 'Bahn mit Hindernis', 'icon_filename': 'bahn_hindernis.png', 'sort_order': 4},
            {'name': 'Gerade', 'description': 'Gerade Bahn', 'icon_filename': 'gerade.png', 'sort_order': 5},
            {'name': 'Berg', 'description': 'Berg-Bahn', 'icon_filename': 'berg.png', 'sort_order': 6},
            {'name': 'Loop', 'description': 'Loop-Bahn', 'icon_filename': 'loop.png', 'sort_order': 7},
            {'name': 'Rampe', 'description': 'Rampen-Bahn', 'icon_filename': 'rampe.png', 'sort_order': 8},
            {'name': 'Tunnel', 'description': 'Tunnel-Bahn', 'icon_filename': 'tunnel.png', 'sort_order': 9},
            {'name': 'S-Kurve', 'description': 'S-Kurven-Bahn', 'icon_filename': 's_kurve.png', 'sort_order': 10},
            {'name': 'Rechtskurve Alt', 'description': 'Alternative Rechtskurve', 'icon_filename': 'rechtskurve.png', 'sort_order': 11},
            {'name': 'Linkskurve Alt', 'description': 'Alternative Linkskurve', 'icon_filename': 'linkskurve.png', 'sort_order': 12},
            {'name': 'Hindernis Alt', 'description': 'Alternative Hindernis-Bahn', 'icon_filename': 'hindernis.png', 'sort_order': 13},
        ]
        
        for tt_data in default_track_types:
            track_type = TrackType(**tt_data)
            db.session.add(track_type)
        
        db.session.commit()
        
        # Get updated count
        new_count = TrackType.query.count()
        
        log_action(f"TrackTypes reset completed - {new_count} types created")
        
        return f"""
        <h1>✅ Track Types Reset Complete</h1>
        <p><strong>{new_count} Track Types</strong> wurden neu erstellt mit deinen PNG-Dateien.</p>
        <h2>🎯 Nächste Schritte:</h2>
        <ol>
            <li>Gehe zu <a href="/settings" style="color: #f8c098;">⚙️ Settings</a></li>
            <li>Bearbeite einen Platz</li>
            <li>Klicke auf ein Track-Icon</li>
            <li>Alle deine PNGs sollten jetzt angezeigt werden!</li>
        </ol>
        <br>
        <a href="/api/debug/track-icons" style="background: #3b5c6c; color: white; padding: 10px 20px; text-decoration: none; border-radius: 8px;">🔍 Debug Check</a>
        <a href="/settings" style="background: #f8c098; color: #2d3748; padding: 10px 20px; text-decoration: none; border-radius: 8px; margin-left: 10px;">⚙️ Settings</a>
        """
        
    except Exception as e:
        db.session.rollback()
        logger.error(f"❌ Force reset error: {str(e)}")
        return f"<h1>Reset Error</h1><p>{str(e)}</p>", 500

# 🔥 NEW: Debug Endpoint für Track Icons
@app.route('/api/debug/track-icons')
def debug_track_icons():
    """Debug endpoint to check track icon files vs database"""
    try:
        # Get all PNG files in track-icons directory
        icon_files = []
        try:
            # Render.com path
            icon_path = os.path.join(os.path.dirname(__file__), 'static', 'track-icons', '*.png')
            png_files = glob.glob(icon_path)
            icon_files = [os.path.basename(f) for f in png_files]
        except Exception as e:
            logger.error(f"Error reading icon files: {e}")
        
        # Get TrackTypes from database
        track_types_db = []
        try:
            track_types = TrackType.query.all()
            track_types_db = [{
                'id': tt.id,
                'name': tt.name,
                'icon_filename': tt.icon_filename,
                'icon_url': tt.icon_url,
                'exists': tt.icon_filename in icon_files
            } for tt in track_types]
        except Exception as e:
            logger.error(f"Error reading track types: {e}")
        
        # Find missing files
        expected_files = [tt['icon_filename'] for tt in track_types_db]
        missing_files = [f for f in expected_files if f not in icon_files]
        extra_files = [f for f in icon_files if f not in expected_files]
        
        debug_info = {
            'status': 'success',
            'render_environment': os.environ.get('ENVIRONMENT', 'not_set'),
            'files_found': sorted(icon_files),
            'track_types': track_types_db,
            'missing_files': missing_files,
            'extra_files': extra_files,
            'files_count': len(icon_files),
            'track_types_count': len(track_types_db),
            'issues': len(missing_files) > 0,
            'icon_path_checked': os.path.join(os.path.dirname(__file__), 'static', 'track-icons'),
            'timestamp': datetime.utcnow().isoformat()
        }
        
        return jsonify(debug_info)
        
    except Exception as e:
        logger.error(f"❌ Debug track icons error: {str(e)}")
        return jsonify({'status': 'error', 'message': str(e)}), 500

@app.route('/db-info')
def db_info():
    """Database information and statistics"""
    try:
        # Connection test
        db_connected = check_database_connection()
        tables_exist = check_tables_exist() if db_connected else False
        
        if not db_connected:
            return jsonify({'error': 'Database not connected'}), 503
        
        # Gather statistics
        stats = {
            'environment': get_environment(),
            'database_type': 'PostgreSQL' if 'postgresql://' in app.config['SQLALCHEMY_DATABASE_URI'] else 'SQLite',
            'connection_status': 'connected',
            'tables_status': 'exist' if tables_exist else 'missing',
            'auto_initialization': 'enabled',
            'tables': {
                'games': Game.query.count() if tables_exist else 0,
                'players': Player.query.count() if tables_exist else 0,
                'scores': Score.query.count() if tables_exist else 0,
                'places': Place.query.count() if tables_exist else 0,
                'track_types': TrackType.query.count() if tables_exist else 0,
                'place_tracks': PlaceTrack.query.count() if tables_exist else 0
            } if tables_exist else 'tables_missing',
            'latest_game': None,
            'timestamp': datetime.utcnow().isoformat()
        }
        
        # Get latest game info
        if tables_exist:
            latest_game = Game.query.order_by(Game.id.desc()).first()
            if latest_game:
                stats['latest_game'] = {
                    'id': latest_game.id,
                    'place': latest_game.place,
                    'date': latest_game.date,
                    'players': len(latest_game.players)
                }
        
        return jsonify(stats)
        
    except Exception as e:
        logger.error(f"❌ DB info error: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/cleanup-standard-places')
def cleanup_standard_places():
    """Development/Admin: Remove all standard places that were auto-created"""
    try:
        if is_production():
            return jsonify({'error': 'Not available in production'}), 403
        
        # Liste der Standard-Places die entfernt werden sollen
        standard_place_names = [
            'Bülach',
            'Zürich Minigolf', 
            'Winterthur Adventure Golf',
            'Rapperswil Minigolf',
            'Bülach Adventure Golf',
            'Minigolf Zürich',
            'Fun Golf Winterthur'
        ]
        
        deleted_count = 0
        deleted_places = []
        
        for place_name in standard_place_names:
            place = Place.query.filter_by(name=place_name).first()
            if place:
                # Prüfe ob Place in Games verwendet wird
                games_count = Game.query.filter_by(place_id=place.id).count()
                
                if games_count == 0:
                    # Sicher zu löschen - keine Games verwenden diesen Place
                    deleted_places.append(f"{place.name} ({place.track_count} Bahnen)")
                    db.session.delete(place)
                    deleted_count += 1
                else:
                    deleted_places.append(f"⚠️ {place.name} BEHALTEN (wird von {games_count} Spielen verwendet)")
        
        db.session.commit()
        
        result_html = f"""
        <h1>🧹 Standard Places Cleanup</h1>
        <h2>✅ Ergebnis:</h2>
        <p><strong>{deleted_count} Places gelöscht</strong></p>
        <ul>
        """
        
        for place_info in deleted_places:
            result_html += f"<li>{place_info}</li>"
        
        result_html += """
        </ul>
        <br>
        <a href="/settings" style="background: #f8c098; color: #2d3748; padding: 10px 20px; text-decoration: none; border-radius: 8px;">⚙️ Zu Settings</a>
        <a href="/" style="background: #3b5c6c; color: white; padding: 10px 20px; text-decoration: none; border-radius: 8px; margin-left: 10px;">🏠 Home</a>
        """
        
        log_action(f"Cleanup: {deleted_count} standard places removed")
        
        return result_html
        
    except Exception as e:
        db.session.rollback()
        logger.error(f"❌ Cleanup error: {str(e)}")
        return f"<h1>Cleanup Error</h1><p>{str(e)}</p>", 500        

# ------------------------------
# Main Application Routes
# ------------------------------

# --- HOME (neuer Hub) ---
@app.route('/')
def home():
    """Neue Startseite / Hub (Neues Spiel, History, Bahnen, MEIN STUFF)"""
    return render_template('home.html')

# --- ALTE STARTSEITE (Spielauswahl Minigolf/Scrabble) ---
@app.route('/classic')
def classic_landing():
    """Alte Landing-Page, erreichbar über den Footer-Link auf der neuen Home"""
    return render_template('landing.html')

# --- MINIGOLF ---
@app.route('/minigolf')
def minigolf_index():
    """Minigolf - New game page"""
    return render_template('index.html')

# --- MEINE BÄLLE (Ball-Verwaltung) ---
@app.route('/balls')
def balls_admin():
    """Ball-Verwaltung 'Meine Bälle' — Spieler kommt per ?player= oder localStorage."""
    return render_template('balls.html')

# --- SCRABBLE ---
@app.route('/scrabble')
def scrabble():
    """Scrabble Score App"""
    return render_template('scrabble.html')


# ------------------------------
# Scrabble API Routes
# ------------------------------

@app.route('/api/scrabble/save', methods=['POST'])
def scrabble_save():
    """Scrabble Spiel speichern"""
    try:
        data = request.get_json()
        
        if not data:
            return jsonify({'status': 'error', 'message': 'No data received'}), 400
        
        game = ScrabbleGame(
            player1_name=data.get('player1', {}).get('name', 'Spieler 1'),
            player1_total=data.get('player1', {}).get('total', 0),
            player1_rounds=data.get('player1', {}).get('moves', 0),
            player2_name=data.get('player2', {}).get('name', 'Spieler 2'),
            player2_total=data.get('player2', {}).get('total', 0),
            player2_rounds=data.get('player2', {}).get('moves', 0),
            winner_name=data.get('winner'),
            is_tie=data.get('isTie', False)
        )
        
        db.session.add(game)
        db.session.commit()
        
        log_action(f"Scrabble game saved: {game.player1_name} vs {game.player2_name}")
        
        return jsonify({
            'status': 'success',
            'game_id': game.id,
            'message': 'Game saved successfully'
        })
        
    except Exception as e:
        db.session.rollback()
        logger.error(f"❌ Scrabble save error: {str(e)}")
        return jsonify({'status': 'error', 'message': 'Failed to save game'}), 500


@app.route('/api/scrabble/history')
def scrabble_history():
    """Scrabble History laden (letzte 50 Spiele)"""
    try:
        games = ScrabbleGame.query.order_by(ScrabbleGame.date.desc()).limit(50).all()
        
        return jsonify({
            'status': 'success',
            'games': [game.to_dict() for game in games]
        })
        
    except Exception as e:
        logger.error(f"❌ Scrabble history error: {str(e)}")
        return jsonify({'status': 'error', 'message': 'Failed to load history'}), 500


@app.route('/api/scrabble/game/<int:game_id>', methods=['DELETE'])
def scrabble_delete(game_id):
    """Scrabble Spiel löschen"""
    try:
        game = ScrabbleGame.query.get_or_404(game_id)
        
        db.session.delete(game)
        db.session.commit()
        
        log_action(f"Scrabble game deleted: {game_id}")
        
        return jsonify({
            'status': 'success',
            'message': 'Game deleted successfully'
        })
        
    except Exception as e:
        db.session.rollback()
        logger.error(f"❌ Scrabble delete error: {str(e)}")
        return jsonify({'status': 'error', 'message': 'Failed to delete game'}), 500


@app.route('/save', methods=['POST'])
def save():
    """Save new game with places support - UPDATED VERSION"""
    try:
        data = request.get_json()
        
        if not data:
            return jsonify({'status': 'error', 'message': 'No data received'}), 400
        
        # Validate required fields
        required_fields = ['date', 'place', 'players']
        for field in required_fields:
            if not data.get(field):
                return jsonify({'status': 'error', 'message': f'Missing required field: {field}'}), 400
        
        place_name = data.get('place').strip()
        track_count = data.get('track_count', 18)
        
        # Find or create place
        place = Place.query.filter_by(name=place_name).first()
        place_id = None
        
        if place:
            place_id = place.id
            # Use place's track count if provided
            track_count = place.track_count
        else:
            # Create new place on-the-fly
            new_place = Place(name=place_name, track_count=track_count)
            db.session.add(new_place)
            db.session.flush()  # Get ID
            new_place.setup_default_tracks()
            place_id = new_place.id
            log_action(f"Auto-created place: {place_name}")
        
        # Create game
        game = Game(
            date=data.get('date'),
            place=place_name,  # Keep for compatibility
            place_id=place_id,  # NEW: Reference to Place
            track_count=track_count
        )
        
        db.session.add(game)
        db.session.flush()  # Get game.id
        
        # Create players and scores (same as before)
        players_data = data.get('players', [])
        
        for player_data in players_data:
            if not player_data.get('name', '').strip():
                db.session.rollback()
                return jsonify({'status': 'error', 'message': 'Player name cannot be empty'}), 400
            
            player = Player(name=player_data['name'].strip(), game=game)
            db.session.add(player)
            db.session.flush()  # Get player.id
            
            # Create initial scores (all 0)
            for track_num in range(1, track_count + 1):
                score = Score(track=track_num, value=0, player=player)
                db.session.add(score)
        
        db.session.commit()
        
        log_action(f"Game created: {place_name} ({len(players_data)} players, {track_count} tracks)")
        
        return jsonify({
            'status': 'success', 
            'game_id': game.id,
            'place_id': place_id,
            'message': f'Game created successfully with {len(players_data)} players'
        })
    
    except Exception as e:
        db.session.rollback()
        logger.error(f"❌ Save error: {str(e)}")
        return jsonify({'status': 'error', 'message': 'Failed to save game'}), 500

@app.route('/score/<int:game_id>')
def score_detail(game_id):
    """Score input page for a specific game"""
    try:
        game = Game.query.get_or_404(game_id)

        # Build score map for template
        score_map = {}
        for player in game.players:
            for score in player.scores:
                score_map[(player.id, score.track)] = score.value

        # Ball-Notes: aktuelle Wahl pro (player_name, track) + Ball-Inventar pro Spieler
        # Nur wenn place_id verfügbar (legacy games haben evtl. keins)
        # Try/Except: falls Migration noch nicht durch, Seite trotzdem anzeigen ohne Ball-UI
        balls_by_player = {}      # player_name -> [ball_dict, ...] (sortiert: zuletzt benutzt zuerst)
        choice_by_player_track = {}  # (player_name, track) -> Haupt-Ball (slot 0, jüngster)
        alt_by_player_track = {}     # (player_name, track) -> Alternativ-Ball (slot 1, jüngster)

        if game.place_id:
            try:
                player_names = list({p.name for p in game.players})

                if player_names:
                    # Inventar
                    balls = (
                        PlayerBall.query
                        .filter(PlayerBall.player_name.in_(player_names))
                        .order_by(PlayerBall.created_at.desc())
                        .all()
                    )
                    for b in balls:
                        balls_by_player.setdefault(b.player_name, []).append(b.to_dict())

                    # Aktuelle Wahl: jüngster Eintrag pro (place, track, player) für dieses place
                    choices = (
                        PlayerTrackChoice.query
                        .filter(
                            PlayerTrackChoice.place_id == game.place_id,
                            PlayerTrackChoice.player_name.in_(player_names),
                        )
                        .order_by(PlayerTrackChoice.created_at.desc())
                        .all()
                    )
                    for c in choices:
                        key = (c.player_name, c.track_number)
                        if (c.slot or 0) == 1:
                            if key not in alt_by_player_track:
                                alt_by_player_track[key] = c.to_dict()
                        else:
                            if key not in choice_by_player_track:
                                choice_by_player_track[key] = c.to_dict()
            except Exception as ball_err:
                db.session.rollback()
                logger.warning(f"⚠️ Ball-Notes nicht verfügbar (vermutlich Migration ausstehend): {ball_err}")
                balls_by_player = {}
                choice_by_player_track = {}
                alt_by_player_track = {}

        log_action(f"Score page accessed for game {game_id}")

        return render_template(
            'score_detail.html',
            game=game,
            players=game.players,
            track_count=game.track_count,
            score_map=score_map,
            balls_by_player=balls_by_player,
            choice_by_player_track=choice_by_player_track,
            alt_by_player_track=alt_by_player_track,
        )

    except Exception as e:
        logger.error(f"❌ Score detail error: {str(e)}")
        return f"<h1>Error</h1><p>Game not found or error loading game.</p>", 404

@app.route('/update_score', methods=['POST'])
def update_score():
    """Update a player's score for a specific track"""
    try:
        data = request.get_json()
        
        # Validate input
        required_fields = ['player_id', 'track', 'value']
        for field in required_fields:
            if field not in data:
                return jsonify({'status': 'error', 'message': f'Missing field: {field}'}), 400
        
        player_id = int(data['player_id'])
        track = int(data['track'])
        value = int(data['value'])
        
        # Validate score value
        if value < 0 or value > 999:  # Reasonable limits
            return jsonify({'status': 'error', 'message': 'Score must be between 0 and 20'}), 400
        
        # Find and update score
        score = Score.query.filter_by(player_id=player_id, track=track).first()
        
        if score:
            score.value = value
        else:
            # Create new score if doesn't exist
            score = Score(player_id=player_id, track=track, value=value)
            db.session.add(score)
        
        db.session.commit()
        
        # Calculate new totals for all players in this game
        player = Player.query.get(player_id)
        game = player.game
        
        totals = {}
        for p in game.players:
            totals[p.id] = p.get_total_score()
        
        log_action(f"Score updated: Player {player_id}, Track {track} = {value}")
        
        return jsonify({
            'status': 'success',
            'totals': totals,
            'message': 'Score updated successfully'
        })
    
    except ValueError:
        return jsonify({'status': 'error', 'message': 'Invalid number format'}), 400
    except Exception as e:
        db.session.rollback()
        logger.error(f"❌ Update score error: {str(e)}")
        return jsonify({'status': 'error', 'message': 'Failed to update score'}), 500

@app.route('/history')
def history():
    """Game history page with track icons support"""
    try:
        games = Game.query.order_by(Game.id.desc()).all()
        
        # Prepare games data for template
        games_data = []
        for game in games:
            # Get track icons for this game
            track_icons = {}
            has_track_config = False
            
            if game.place_config and game.place_config.place_tracks:
                has_track_config = True
                place_track_map = {pt.track_number: pt for pt in game.place_config.place_tracks}
                
                for track_num in range(1, game.track_count + 1):
                    if track_num in place_track_map:
                        track_icons[track_num] = place_track_map[track_num].track_type.icon_url
                    else:
                        track_icons[track_num] = '/static/track-icons/bahn_placeholder.png'
            else:
                # Default icons for legacy games
                for track_num in range(1, game.track_count + 1):
                    track_icons[track_num] = '/static/track-icons/bahn_placeholder.png'
            
            game_data = {
                'id': game.id,
                'date': game.date,
                'place': game.place,
                'place_id': game.place_id,
                'track_count': game.track_count,
                'players': [{'name': p.name, 'total': p.get_total_score()} for p in game.players],
                'player_count': len(game.players),
                'has_track_config': has_track_config,
                'track_icons': track_icons
            }
            games_data.append(game_data)
        
        log_action(f"History accessed ({len(games)} games)")
        
        return render_template('history.html', games=games, games_data=games_data)
        
    except Exception as e:
        logger.error(f"❌ History error: {str(e)}")
        return f"<h1>Error</h1><p>Failed to load game history.</p>", 500

@app.route('/delete_game/<int:game_id>', methods=['POST'])
def delete_game(game_id):
    """Delete a game and all associated data"""
    try:
        game = Game.query.get_or_404(game_id)
        game_info = f"{game.place} on {game.date}"
        
        db.session.delete(game)
        db.session.commit()
        
        log_action(f"Game deleted: {game_info}")
        
        return jsonify({'status': 'success', 'message': 'Game deleted successfully'})
        
    except Exception as e:
        db.session.rollback()
        logger.error(f"❌ Delete error: {str(e)}")
        return jsonify({'status': 'error', 'message': 'Failed to delete game'}), 500

@app.route('/results/<int:game_id>')
def game_results(game_id):
    """Final results page for a game"""
    try:
        game = Game.query.get_or_404(game_id)
        
        # Calculate results
        results = []
        for player in game.players:
            total = player.get_total_score()
            result = {
                'name': player.name,
                'total': total,
                'scores': {score.track: score.value for score in player.scores}
            }
            results.append(result)
        
        # Sort by total score (lowest wins)
        results.sort(key=lambda x: x['total'])
        
        # Determine winners (handle ties)
        winners = []
        if results and results[0]['total'] > 0:
            min_score = results[0]['total']
            winners = [r for r in results if r['total'] == min_score]
            
            # Mark winners and ties
            for result in results:
                result['is_winner'] = result['total'] == min_score
                result['is_tie'] = len(winners) > 1 and result['is_winner']
        
        log_action(f"Results viewed for game {game_id}")
        
        return render_template('results.html', game=game, results=results, winners=winners)
        
    except Exception as e:
        logger.error(f"❌ Results error: {str(e)}")
        return f"<h1>Error</h1><p>Game not found or error loading results.</p>", 404

# ------------------------------
# API ENDPOINTS (COMPLETE VERSION WITH ALL CRUD OPERATIONS)
# ------------------------------

@app.route('/api/places', methods=['GET'])
def get_places():
    """Real places API for autocomplete"""
    try:
        places = Place.query.order_by(Place.is_default.desc(), Place.name).all()
        places_data = []
        
        for place in places:
            places_data.append({
                'id': place.id,
                'name': place.name,
                'track_count': place.track_count,
                'is_default': place.is_default,
                'has_custom_config': len(place.place_tracks) > 0
            })
        
        return jsonify({
            'status': 'success',
            'places': places_data
        })
        
    except Exception as e:
        logger.error(f"❌ Get places error: {str(e)}")
        return jsonify({'status': 'error', 'message': 'Failed to load places'}), 500

@app.route('/api/places', methods=['POST'])
def create_place():
    """Create new place"""
    try:
        data = request.get_json()
        
        if not data or not data.get('name'):
            return jsonify({'status': 'error', 'message': 'Name is required'}), 400
        
        # Check if place already exists
        existing = Place.query.filter_by(name=data['name']).first()
        if existing:
            return jsonify({'status': 'error', 'message': 'Place already exists'}), 400
        
        # Create new place
        place = Place(
            name=data['name'],
            track_count=data.get('track_count', 18),
            is_default=data.get('is_default', False)
        )
        
        db.session.add(place)
        db.session.flush()  # Get ID
        
        # Setup default tracks
        place.setup_default_tracks()
        
        db.session.commit()
        
        log_action(f"Place created via API: {place.name}")
        
        return jsonify({
            'status': 'success',
            'place_id': place.id,
            'message': 'Place created successfully'
        })
        
    except Exception as e:
        db.session.rollback()
        logger.error(f"❌ Create place error: {str(e)}")
        return jsonify({'status': 'error', 'message': str(e)}), 500

@app.route('/api/places/<int:place_id>', methods=['PUT'])
def update_place(place_id):
    """Update existing place"""
    try:
        place = Place.query.get_or_404(place_id)
        data = request.get_json()
        
        if not data:
            return jsonify({'status': 'error', 'message': 'No data provided'}), 400
        
        # Update place fields
        if 'name' in data and data['name'] != place.name:
            # Check for duplicate names
            existing = Place.query.filter_by(name=data['name']).first()
            if existing and existing.id != place.id:
                return jsonify({'status': 'error', 'message': 'Place name already exists'}), 400
            place.name = data['name']
        
        if 'track_count' in data:
            old_count = place.track_count
            new_count = int(data['track_count'])
            place.track_count = new_count
            
            # Handle track count changes
            if new_count != old_count:
                # Remove excess tracks
                if new_count < old_count:
                    excess_tracks = PlaceTrack.query.filter(
                        PlaceTrack.place_id == place.id,
                        PlaceTrack.track_number > new_count
                    ).all()
                    for track in excess_tracks:
                        db.session.delete(track)
                
                # Add missing tracks
                elif new_count > old_count:
                    default_type = TrackType.query.filter_by(is_default=True).first()
                    if default_type:
                        for track_num in range(old_count + 1, new_count + 1):
                            new_track = PlaceTrack(
                                place=place,
                                track_number=track_num,
                                track_type=default_type
                            )
                            db.session.add(new_track)
        
        if 'is_default' in data:
            place.is_default = bool(data['is_default'])
        
        db.session.commit()
        
        log_action(f"Place updated via API: {place.name}")
        
        return jsonify({
            'status': 'success',
            'message': 'Place updated successfully'
        })
        
    except Exception as e:
        db.session.rollback()
        logger.error(f"❌ Update place error: {str(e)}")
        return jsonify({'status': 'error', 'message': str(e)}), 500

@app.route('/api/places/<int:place_id>', methods=['DELETE'])
def delete_place_api(place_id):
    """Delete place"""
    try:
        place = Place.query.get_or_404(place_id)
        
        # Check if place is used in games
        games_count = Game.query.filter_by(place_id=place.id).count()
        if games_count > 0:
            return jsonify({
                'status': 'error', 
                'message': f'Cannot delete place - it is used in {games_count} games'
            }), 400
        
        place_name = place.name
        db.session.delete(place)
        db.session.commit()
        
        log_action(f"Place deleted via API: {place_name}")
        
        return jsonify({
            'status': 'success',
            'message': 'Place deleted successfully'
        })
        
    except Exception as e:
        db.session.rollback()
        logger.error(f"❌ Delete place error: {str(e)}")
        return jsonify({'status': 'error', 'message': str(e)}), 500

@app.route('/api/track-types', methods=['GET'])  
def get_track_types():
    """Real track types API"""
    try:
        track_types = TrackType.query.order_by(TrackType.sort_order, TrackType.name).all()
        track_types_data = []
        
        for tt in track_types:
            track_types_data.append({
                'id': tt.id,
                'name': tt.name,
                'description': tt.description,
                'icon_url': tt.icon_url,
                'icon_filename': tt.icon_filename,
                'is_default': tt.is_default,
                'is_placeholder': tt.is_placeholder
            })
        
        return jsonify({
            'status': 'success',
            'track_types': track_types_data
        })
        
    except Exception as e:
        logger.error(f"❌ Get track types error: {str(e)}")
        return jsonify({'status': 'error', 'message': 'Failed to load track types'}), 500

@app.route('/api/places/<int:place_id>/tracks')
def get_place_track_config(place_id):
    """Get track configuration for a specific place"""
    try:
        place = Place.query.get_or_404(place_id)
        
        track_config = []
        place_track_map = {pt.track_number: pt for pt in place.place_tracks}
        
        for track_num in range(1, place.track_count + 1):
            if track_num in place_track_map:
                pt = place_track_map[track_num]
                track_config.append({
                    'track_number': track_num,
                    'track_type_id': pt.track_type_id,
                    'track_type_name': pt.track_type.name,
                    'icon_url': pt.track_type.icon_url
                })
            else:
                # Default fallback
                default_type = TrackType.query.filter_by(is_default=True).first()
                track_config.append({
                    'track_number': track_num,
                    'track_type_id': default_type.id if default_type else None,
                    'track_type_name': default_type.name if default_type else 'Standard',
                    'icon_url': default_type.icon_url if default_type else '/static/track-icons/bahn_placeholder.png'
                })
        
        return jsonify({
            'status': 'success',
            'place': {
                'id': place.id,
                'name': place.name,
                'track_count': place.track_count
            },
            'track_config': track_config
        })
        
    except Exception as e:
        logger.error(f"❌ Get place track config error: {str(e)}")
        return jsonify({'status': 'error', 'message': str(e)}), 500

@app.route('/api/places/<int:place_id>/tracks/<int:track_number>', methods=['PUT'])
def update_place_track_type(place_id, track_number):
    """Update track type for specific track at place"""
    try:
        place = Place.query.get_or_404(place_id)
        data = request.get_json()
        
        if not data or 'track_type_id' not in data:
            return jsonify({'status': 'error', 'message': 'track_type_id is required'}), 400
        
        track_type_id = int(data['track_type_id'])
        track_type = TrackType.query.get_or_404(track_type_id)
        
        # Find or create place track
        place_track = PlaceTrack.query.filter_by(
            place_id=place.id,
            track_number=track_number
        ).first()
        
        if place_track:
            place_track.track_type = track_type
        else:
            place_track = PlaceTrack(
                place=place,
                track_number=track_number,
                track_type=track_type
            )
            db.session.add(place_track)
        
        db.session.commit()
        
        log_action(f"Track {track_number} at {place.name} updated to {track_type.name}")
        
        return jsonify({
            'status': 'success',
            'message': f'Track {track_number} updated to {track_type.name}'
        })
        
    except Exception as e:
        db.session.rollback()
        logger.error(f"❌ Update track type error: {str(e)}")
        return jsonify({'status': 'error', 'message': str(e)}), 500

@app.route('/api/places/<int:place_id>/tracks', methods=['PUT'])
def update_place_track_config(place_id):
    """Update complete track configuration for place"""
    try:
        place = Place.query.get_or_404(place_id)
        data = request.get_json()
        
        if not data or 'track_config' not in data:
            return jsonify({'status': 'error', 'message': 'track_config is required'}), 400
        
        track_config = data['track_config']
        updated_tracks = 0
        
        for track_data in track_config:
            track_number = track_data.get('track_number')
            track_type_id = track_data.get('track_type_id')
            
            if not track_number or not track_type_id:
                continue
            
            # Find or create place track
            place_track = PlaceTrack.query.filter_by(
                place_id=place.id,
                track_number=track_number
            ).first()
            
            track_type = TrackType.query.get(track_type_id)
            if not track_type:
                continue
            
            if place_track:
                place_track.track_type = track_type
            else:
                place_track = PlaceTrack(
                    place=place,
                    track_number=track_number,
                    track_type=track_type
                )
                db.session.add(place_track)
            
            updated_tracks += 1
        
        db.session.commit()
        
        log_action(f"Track configuration updated for {place.name}: {updated_tracks} tracks")
        
        return jsonify({
            'status': 'success',
            'updated_tracks': updated_tracks,
            'message': f'Track configuration updated - {updated_tracks} tracks'
        })
        
    except Exception as e:
        db.session.rollback()
        logger.error(f"❌ Update track config error: {str(e)}")
        return jsonify({'status': 'error', 'message': str(e)}), 500

@app.route('/api/status')
def api_status():
    """API status endpoint"""
    return health_check()

@app.route('/settings')
def settings():
    """Settings page with real data"""
    try:
        # Get current statistics
        stats = {
            'places_count': Place.query.count(),
            'track_types_count': TrackType.query.count(),
            'games_count': Game.query.count(),
            'players_count': Player.query.count(),
            'scores_count': Score.query.count()
        }
        
        # Get places and track types for settings
        places = Place.query.order_by(Place.is_default.desc(), Place.name).all()
        track_types = TrackType.query.order_by(TrackType.sort_order).all()
        
        return render_template('settings.html', 
                             stats=stats, 
                             places=places, 
                             track_types=track_types)
        
    except Exception as e:
        logger.error(f"❌ Settings page error: {str(e)}")
        return f"<h1>Settings</h1><p>Error loading settings: {str(e)}</p>", 500

# ------------------------------
# Error Handlers
# ------------------------------

@app.errorhandler(404)
def not_found_error(error):
    """Handle 404 errors"""
    return render_template('404.html'), 404

@app.errorhandler(500)
def internal_error(error):
    """Handle 500 errors"""
    db.session.rollback()
    logger.error(f"❌ Internal server error: {str(error)}")
    return render_template('500.html'), 500

@app.errorhandler(Exception)
def handle_exception(e):
    """Handle unexpected exceptions in production"""
    logger.error(f"❌ Unhandled exception: {str(e)}")
    
    if is_development():
        # In development, show full error
        raise e
    else:
        # In production, show generic error page
        db.session.rollback()
        return f"<h1>🏌️ Gopher Minigolf</h1><p>Something went wrong. Please try again.</p>", 500

# ------------------------------
# Ball Notes API (PlayerBall + PlayerTrackChoice)
# ------------------------------

@app.route('/api/profiles', methods=['GET'])
def api_profiles_list():
    """Alle Profile (kanonische Spieler-Identitäten)."""
    profiles = Profile.query.order_by(Profile.sort_order, Profile.name).all()
    return jsonify({'status': 'success', 'profiles': [p.to_dict() for p in profiles]})


@app.route('/api/balls', methods=['GET'])
def api_balls_list():
    """Liste aller Bälle eines Spielers (sortiert nach 'zuletzt benutzt')."""
    player_name = (request.args.get('player_name') or '').strip()
    if not player_name:
        return jsonify({'status': 'error', 'message': 'player_name required'}), 400

    balls = (
        PlayerBall.query
        .filter_by(player_name=player_name)
        .order_by(PlayerBall.created_at.desc())
        .all()
    )
    return jsonify({'status': 'success', 'balls': [b.to_dict() for b in balls]})


@app.route('/api/balls', methods=['POST'])
def api_balls_create():
    """Neuen Ball anlegen. Bei Duplikat (player_name+label) den existierenden zurückgeben."""
    try:
        data = request.get_json() or {}
        player_name = (data.get('player_name') or '').strip()
        label = (data.get('label') or '').strip()
        color_hex = (data.get('color_hex') or '').strip() or None
        image_data = data.get('image_data') or None
        description = data.get('description')
        if description is not None:
            description = description.strip() or None

        if not player_name or not label:
            return jsonify({'status': 'error', 'message': 'player_name und label required'}), 400

        existing = PlayerBall.query.filter_by(player_name=player_name, label=label).first()
        if existing:
            # Optional: Farbe/Foto/Beschreibung aktualisieren, wenn neu mitgegeben
            if color_hex and existing.color_hex != color_hex:
                existing.color_hex = color_hex
            if image_data is not None:
                existing.image_data = image_data
            if description is not None:
                existing.description = description
            db.session.commit()
            return jsonify({'status': 'success', 'ball': existing.to_dict(), 'created': False})

        ball = PlayerBall(player_name=player_name, label=label, color_hex=color_hex, image_data=image_data, description=description)
        db.session.add(ball)
        db.session.commit()
        log_action(f"Ball created: {player_name} / {label}")
        return jsonify({'status': 'success', 'ball': ball.to_dict(), 'created': True})

    except Exception as e:
        db.session.rollback()
        logger.error(f"❌ api_balls_create error: {str(e)}")
        return jsonify({'status': 'error', 'message': 'Failed to create ball'}), 500


@app.route('/api/balls/<int:ball_id>', methods=['PUT', 'PATCH'])
def api_balls_update(ball_id):
    """Ball-Details (label und/oder color_hex) aktualisieren."""
    try:
        ball = PlayerBall.query.get(ball_id)
        if not ball:
            return jsonify({'status': 'error', 'message': 'ball not found'}), 404

        data = request.get_json() or {}
        new_label = data.get('label')
        new_color = data.get('color_hex')

        if new_label is not None:
            new_label = new_label.strip()
            if not new_label:
                return jsonify({'status': 'error', 'message': 'label darf nicht leer sein'}), 400
            # Konflikt-Check: anderer Ball mit gleichem Label desselben Spielers?
            conflict = (
                PlayerBall.query
                .filter(
                    PlayerBall.player_name == ball.player_name,
                    PlayerBall.label == new_label,
                    PlayerBall.id != ball.id,
                )
                .first()
            )
            if conflict:
                return jsonify({'status': 'error', 'message': f'Spieler hat bereits einen Ball "{new_label}"'}), 409
            ball.label = new_label

        if new_color is not None:
            new_color = new_color.strip() or None
            ball.color_hex = new_color

        new_image = data.get('image_data')
        if new_image is not None:
            ball.image_data = new_image or None  # leerer String -> Foto entfernen

        new_desc = data.get('description')
        if new_desc is not None:
            ball.description = new_desc.strip() or None

        db.session.commit()
        log_action(f"Ball {ball.id} aktualisiert: {ball.player_name} / {ball.label}")
        return jsonify({'status': 'success', 'ball': ball.to_dict()})

    except Exception as e:
        db.session.rollback()
        logger.error(f"❌ api_balls_update error: {str(e)}")
        return jsonify({'status': 'error', 'message': 'Failed to update ball'}), 500


@app.route('/api/balls/<int:ball_id>', methods=['DELETE'])
def api_balls_delete(ball_id):
    """Ball löschen. Referenzen in PlayerTrackChoice werden auf NULL gesetzt
    (Historie bleibt erhalten, nur ohne Ball-Verknüpfung).
    """
    try:
        ball = PlayerBall.query.get(ball_id)
        if not ball:
            return jsonify({'status': 'error', 'message': 'ball not found'}), 404

        # Alle Track-Choices mit Verweis auf diesen Ball: ball_id = NULL
        affected = PlayerTrackChoice.query.filter_by(ball_id=ball.id).update({'ball_id': None})

        db.session.delete(ball)
        db.session.commit()
        log_action(f"Ball gelöscht: {ball.player_name} / {ball.label} (Refs auf NULL: {affected})")
        return jsonify({'status': 'success', 'deleted_id': ball_id, 'unlinked_choices': affected})

    except Exception as e:
        db.session.rollback()
        logger.error(f"❌ api_balls_delete error: {str(e)}")
        return jsonify({'status': 'error', 'message': 'Failed to delete ball'}), 500


@app.route('/api/track-choice', methods=['POST'])
def api_track_choice_create():
    """Append-only: neue Wahl (Ball + optional Notiz) für (place, track, player).

    Nimmt entweder ball_id (existierender Ball) oder ball (label/color) für inline-Anlage.
    """
    try:
        data = request.get_json() or {}
        place_id = data.get('place_id')
        track_number = data.get('track_number')
        player_name = (data.get('player_name') or '').strip()
        ball_id = data.get('ball_id')
        ball_inline = data.get('ball')  # {label, color_hex} optional
        note = data.get('note')
        if note is not None:
            note = note.strip() or None
        try:
            slot = int(data.get('slot') or 0)
        except (TypeError, ValueError):
            slot = 0

        if not place_id or not track_number or not player_name:
            return jsonify({'status': 'error', 'message': 'place_id, track_number, player_name required'}), 400

        # Place validieren
        place = Place.query.get(int(place_id))
        if not place:
            return jsonify({'status': 'error', 'message': 'place not found'}), 404

        # Inline-Ball anlegen oder existierenden nehmen
        if not ball_id and ball_inline:
            label = (ball_inline.get('label') or '').strip()
            color_hex = (ball_inline.get('color_hex') or '').strip() or None
            if label:
                existing = PlayerBall.query.filter_by(player_name=player_name, label=label).first()
                if existing:
                    if color_hex and existing.color_hex != color_hex:
                        existing.color_hex = color_hex
                    ball_id = existing.id
                else:
                    new_ball = PlayerBall(player_name=player_name, label=label, color_hex=color_hex)
                    db.session.add(new_ball)
                    db.session.flush()
                    ball_id = new_ball.id

        if not ball_id and not note:
            return jsonify({'status': 'error', 'message': 'ball oder note required'}), 400

        choice = PlayerTrackChoice(
            place_id=int(place_id),
            track_number=int(track_number),
            player_name=player_name,
            ball_id=int(ball_id) if ball_id else None,
            note=note,
            slot=slot,
        )
        db.session.add(choice)
        db.session.commit()
        log_action(f"TrackChoice: {player_name} @ place={place_id} bahn={track_number}")
        return jsonify({'status': 'success', 'choice': choice.to_dict()})

    except Exception as e:
        db.session.rollback()
        logger.error(f"❌ api_track_choice_create error: {str(e)}")
        return jsonify({'status': 'error', 'message': 'Failed to save choice'}), 500


@app.route('/api/track-choice/history', methods=['GET'])
def api_track_choice_history():
    """Historie für (place, track, player) — neuester Eintrag zuerst."""
    place_id = request.args.get('place_id', type=int)
    track_number = request.args.get('track_number', type=int)
    player_name = (request.args.get('player_name') or '').strip()

    if not place_id or not track_number or not player_name:
        return jsonify({'status': 'error', 'message': 'place_id, track_number, player_name required'}), 400

    rows = (
        PlayerTrackChoice.query
        .filter_by(place_id=place_id, track_number=track_number, player_name=player_name)
        .order_by(PlayerTrackChoice.created_at.desc())
        .all()
    )
    return jsonify({'status': 'success', 'history': [r.to_dict() for r in rows]})


# ------------------------------
# Application Startup & Initialization
# ------------------------------

def initialize_app():
    """Initialize the application on startup"""
    try:
        log_action("🚀 Gopher Minigolf App initializing")
        
        # Test database connection
        if check_database_connection():
            log_action("Database connection successful")
            
            # Check and create tables if needed
            if not check_tables_exist():
                log_action("Creating database tables on startup")
                success = safe_database_init()
                if success:
                    log_action("✅ Startup database initialization successful")
                else:
                    logger.error("❌ Startup database initialization failed")
            else:
                log_action("Database tables already exist")
        else:
            logger.error("❌ Database connection failed on startup")
            
        log_action("✅ Application initialization complete")
        
    except Exception as e:
        logger.error(f"❌ Application initialization error: {str(e)}")

# Initialize app when module is imported (works with Gunicorn)
with app.app_context():
    try:
        initialize_app()
    except Exception as e:
        logger.error(f"⚠️ App context initialization warning: {e}")

if __name__ == '__main__':
    # Configure for local development or manual run
    port = int(os.environ.get('PORT', 5001))
    debug = is_development()
    
    startup_msg = f"🏌️ Starting Gopher Minigolf App"
    if is_production():
        startup_msg += f" in PRODUCTION mode on port {port} 🛡️"
    else:
        startup_msg += f" in DEVELOPMENT mode on port {port} 🔧"
    
    logger.info(startup_msg)
    logger.info("📋 Auto-initialization is ENABLED - no manual /initdb needed!")
    
    # Render.com uses PORT environment variable
    app.run(host='0.0.0.0', port=port, debug=debug)
else:
    # When run via Gunicorn (Render.com)
    logger.info("🚀 Starting via Gunicorn for Render.com")
    
    # Ensure database is initialized for Gunicorn
    try:
        with app.app_context():
            if not check_tables_exist():
                logger.info("🔧 Gunicorn startup: Creating tables")
                safe_database_init()
    except Exception as e:
        logger.error(f"❌ Gunicorn startup error: {e}")