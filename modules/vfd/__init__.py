# modules/vfd/__init__.py
import os
from flask import Blueprint

# Configures this folder to act as a self-contained web component package
vfd_blueprint = Blueprint(
    'vfd', 
    __name__,
    template_folder='.',       # Tells the server to look right here for html files
    static_folder='.',         # Tells the server to look right here for js assets
    static_url_path='/vfd_static'
)

from . import vfd_routes