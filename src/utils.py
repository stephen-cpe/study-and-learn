"""
Utility functions for the Study-and-Learn MVP.
"""
import os

# Allowed file extensions for upload
ALLOWED_EXTENSIONS = {'txt', 'md', 'pdf', 'docx', 'pptx', 'png', 'jpg', 'jpeg'}


def allowed_file(filename):
    """Check if the file extension is allowed.
    
    Args:
        filename (str): The filename to check
        
    Returns:
        bool: True if file extension is allowed, False otherwise
    """
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS