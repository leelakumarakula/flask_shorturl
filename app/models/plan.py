from ..extensions import db

class Plan(db.Model):
    __tablename__ = 'plans'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), nullable=False, unique=True)  # Free, Pro, Premium
    price_usd = db.Column(db.Float, default=0.0)
    price_inr = db.Column(db.Float, default=0.0)

    # Limits
    max_links = db.Column(db.Integer, default=5)
    max_qrs = db.Column(db.Integer, default=2)
    max_custom_links = db.Column(db.Integer, default=2)
    max_qr_with_logo = db.Column(db.Integer, default=0)
    max_editable_links = db.Column(db.Integer, default=0)  # -1 for unlimited

    # Permissions
    allow_qr_styling = db.Column(db.Boolean, default=False)
    allow_analytics = db.Column(db.Boolean, default=False)
    show_individual_stats = db.Column(db.Boolean, default=False)
    allow_api_access = db.Column(db.Boolean, default=False)

    # Config
    analytics_level = db.Column(db.String(20), default='none')  # none, basic, detailed

    # Razorpay Plan Details
    period = db.Column(db.String(50), nullable=True)  # daily, weekly, monthly, yearly
    interval = db.Column(db.Integer, nullable=True)
    item = db.Column(db.Text, nullable=True)  # JSON string
    notes = db.Column(db.Text, nullable=True)  # JSON string

    def __repr__(self):
        return f"<Plan {self.name}>"
