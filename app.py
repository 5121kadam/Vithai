# ganesh_ar.py (updated version)
import cv2
import numpy as np
import torch
import torch.nn as nn
from torchvision import models, transforms
from flask import Flask, render_template, request, send_file, jsonify
from PIL import Image
import io
import os
import base64

class Idol:
    def __init__(self, id, name, image_path, size):
        self.id = id
        self.name = name
        self.image_path = image_path
        self.size = size
        self._image = None
    
    @property
    def image(self):
        if self._image is None:
            self._image = cv2.imread(self.image_path)
            if self._image is None:
                raise ValueError(f"Could not load image at {self.image_path}")
            self._image = cv2.cvtColor(self._image, cv2.COLOR_BGR2RGB)
        return self._image

class WallSegmenter:
    def __init__(self):
        self.model = models.segmentation.deeplabv3_resnet50(pretrained=True)
        self.model.eval()
        self.transform = transforms.Compose([
            transforms.ToTensor(),
            transforms.Normalize(mean=[0.485, 0.456, 0.406], 
                                 std=[0.229, 0.224, 0.225]),
        ])
    
    def segment(self, image):
        """Identify walls in the image"""
        input_tensor = self.transform(image)
        input_batch = input_tensor.unsqueeze(0)
        
        with torch.no_grad():
            output = self.model(input_batch)['out'][0]
        
        wall_mask = (output.argmax(0) == 0).byte().cpu().numpy()  # Class 0: wall
        return wall_mask

class DecorationGenerator:
    def __init__(self):
        self.patterns = [
            self._create_diagonal_pattern,
            self._create_geometric_pattern,
            self._create_floral_pattern
        ]
    
    def generate(self, wall_img, idol_img):
        """Generate decorative background based on idol colors"""
        # Extract dominant colors
        colors = self._get_dominant_colors(idol_img)
        bg_color, pattern_color = colors[0], colors[-1]
        
        # Create base background
        h, w = wall_img.shape[:2]
        background = np.full((h, w, 3), bg_color, dtype=np.uint8)
        
        # Add decorative pattern
        pattern_func = np.random.choice(self.patterns)
        pattern = pattern_func((h, w), pattern_color)
        
        # Blend with wall
        blended = cv2.addWeighted(wall_img, 0.7, background, 0.3, 0)
        result = cv2.addWeighted(blended, 0.8, pattern, 0.2, 0)
        return result
    
    def _get_dominant_colors(self, image, n_colors=3):
        """Extract dominant colors using k-means clustering"""
        pixels = image.reshape(-1, 3).astype(np.float32)
        
        criteria = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 200, 0.1)
        _, labels, centers = cv2.kmeans(
            pixels, n_colors, None, criteria, 10, cv2.KMEANS_RANDOM_CENTERS
        )
        
        return centers.astype(np.uint8)
    
    def _create_diagonal_pattern(self, size, color):
        pattern = np.zeros((*size, 3), dtype=np.uint8)
        for i in range(0, size[1], 100):
            cv2.line(pattern, (i, 0), (0, i//2), color.tolist(), 10)
        return pattern
    
    def _create_geometric_pattern(self, size, color):
        pattern = np.zeros((*size, 3), dtype=np.uint8)
        for y in range(0, size[0], 100):
            for x in range(0, size[1], 100):
                if (x//100 + y//100) % 2 == 0:
                    cv2.circle(pattern, (x+50, y+50), 40, color.tolist(), -1)
        return pattern
    
    def _create_floral_pattern(self, size, color):
        pattern = np.zeros((*size, 3), dtype=np.uint8)
        for y in range(50, size[0], 100):
            for x in range(50, size[1], 100):
                # Draw flower-like pattern
                cv2.circle(pattern, (x, y), 20, color.tolist(), -1)
                for angle in range(0, 360, 45):
                    rad = np.deg2rad(angle)
                    end_x = int(x + 35 * np.cos(rad))
                    end_y = int(y + 35 * np.sin(rad))
                    cv2.line(pattern, (x, y), (end_x, end_y), color.tolist(), 8)
        return pattern

class IdolPlacer:
    def __init__(self):
        self.shadow_intensity = 0.7
    
    def place(self, background, idol, mask, position):
        """Place idol on the background with realistic effects"""
        # Resize idol based on position
        idol = self._resize_idol(idol, background.shape, position['scale'])
        
        # Calculate placement position
        x, y = self._calculate_position(background, idol, position)
        
        # Create ROI
        roi_y1, roi_y2 = y - idol.shape[0], y
        roi_x1, roi_x2 = x - idol.shape[1]//2, x + idol.shape[1]//2
        
        # Ensure within bounds
        roi_y1, roi_x1 = max(0, roi_y1), max(0, roi_x1)
        roi_y2, roi_x2 = min(background.shape[0], roi_y2), min(background.shape[1], roi_x2)
        
        # Adjust idol size if needed
        idol = idol[:roi_y2-roi_y1, :roi_x2-roi_x1]
        
        # Create mask
        idol_gray = cv2.cvtColor(idol, cv2.COLOR_RGB2GRAY)
        _, idol_mask = cv2.threshold(idol_gray, 10, 255, cv2.THRESH_BINARY)
        
        # Apply wall mask
        roi_mask = mask[roi_y1:roi_y2, roi_x1:roi_x2]
        final_mask = cv2.bitwise_and(idol_mask, roi_mask)
        
        # Add shadow effect
        shadow = self._create_shadow(idol, final_mask)
        
        # Composite images
        background_roi = background[roi_y1:roi_y2, roi_x1:roi_x2]
        composite = cv2.addWeighted(background_roi, 1.0, shadow, self.shadow_intensity, 0)
        composite = cv2.bitwise_and(composite, composite, mask=cv2.bitwise_not(final_mask))
        idol_part = cv2.bitwise_and(idol, idol, mask=final_mask)
        result_roi = cv2.add(composite, idol_part)
        
        # Insert into background
        result = background.copy()
        result[roi_y1:roi_y2, roi_x1:roi_x2] = result_roi
        return result
    
    def _resize_idol(self, idol, bg_shape, scale):
        """Resize idol while maintaining aspect ratio"""
        bg_height = bg_shape[0]
        new_height = int(bg_height * scale)
        h, w = idol.shape[:2]
        ratio = new_height / h
        new_width = int(w * ratio)
        return cv2.resize(idol, (new_width, new_height))
    
    def _calculate_position(self, background, idol, position):
        """Convert relative position to absolute coordinates"""
        height, width = background.shape[:2]
        x = int(position['x'] * width)
        y = int(position['y'] * height)
        return x, y
    
    def _create_shadow(self, idol, mask):
        """Create shadow effect for realism"""
        shadow = np.zeros_like(idol)
        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (15, 15))
        dilated_mask = cv2.dilate(mask, kernel, iterations=1)
        shadow[dilated_mask > 0] = [20, 20, 20]
        return shadow

class ARViewer:
    def __init__(self):
        self.segmenter = WallSegmenter()
        self.decorator = DecorationGenerator()
        self.placer = IdolPlacer()
    
    def visualize(self, wall_img, idol_img, position):
        """Full processing pipeline"""
        # Convert to RGB
        wall_img = cv2.cvtColor(wall_img, cv2.COLOR_BGR2RGB)
        
        # Process images
        wall_mask = self.segmenter.segment(wall_img)
        decorated_wall = self.decorator.generate(wall_img, idol_img)
        result = self.placer.place(decorated_wall, idol_img, wall_mask, position)
        
        return result

class GaneshARApp:
    def __init__(self):
        self.app = Flask(__name__)
        self.idols = [
            Idol(1, "Golden Ganesh", "static/idols/golden.jpg", "12 inches"),
            Idol(2, "Marble Ganesh", "static/idols/marble.jpg", "18 inches")
        ]
        self.viewer = ARViewer()
        self._setup_routes()
    
    def _setup_routes(self):
        self.app.route('/')(self.home)
        self.app.route('/ar/<int:idol_id>')(self.ar_view)
        self.app.route('/process', methods=['POST'])(self.process)
        self.app.route('/get_idol/<int:idol_id>')(self.get_idol_image)
    
    def home(self):
        return render_template('index.html', idols=self.idols)
    
    def ar_view(self, idol_id):
        idol = next((i for i in self.idols if i.id == idol_id), None)
        return render_template('ar.html', idol=idol)
    
    def get_idol_image(self, idol_id):
        idol = next((i for i in self.idols if i.id == idol_id), None)
        if idol:
            with open(idol.image_path, 'rb') as f:
                return send_file(
                    io.BytesIO(f.read()),
                    mimetype='image/jpeg',
                    as_attachment=False
                )
        return jsonify({'error': 'Idol not found'}), 404
    
    def process(self):
        try:
            # Get position data
            position = {
                'x': float(request.form.get('x', 0.5)),
                'y': float(request.form.get('y', 0.8)),
                'scale': float(request.form.get('scale', 0.3))
            }
            
            # Get idol image (from ID)
            idol_id = int(request.form.get('idol_id'))
            idol = next((i for i in self.idols if i.id == idol_id), None)
            if not idol:
                return jsonify({'error': 'Idol not found'}), 404
            
            # Get wall image
            if 'wall' not in request.files:
                return jsonify({'error': 'No wall image provided'}), 400
                
            wall_file = request.files['wall']
            if wall_file.filename == '':
                return jsonify({'error': 'No selected file'}), 400
                
            try:
                wall_img = Image.open(wall_file)
                wall_img = np.array(wall_img)
                if len(wall_img.shape) == 2:  # Convert grayscale to RGB
                    wall_img = cv2.cvtColor(wall_img, cv2.COLOR_GRAY2RGB)
                elif wall_img.shape[2] == 4:  # Remove alpha channel
                    wall_img = wall_img[:, :, :3]
            except Exception as e:
                return jsonify({'error': f'Invalid image file: {str(e)}'}), 400
            
            # Process visualization
            result = self.viewer.visualize(wall_img, idol.image, position)
            
            # Convert to base64 for response
            _, buffer = cv2.imencode('.jpg', cv2.cvtColor(result, cv2.COLOR_RGB2BGR))
            result_base64 = base64.b64encode(buffer).decode('utf-8')
            
            return jsonify({
                'result': f'data:image/jpeg;base64,{result_base64}'
            })
            
        except Exception as e:
            return jsonify({'error': str(e)}), 500
    
    def run(self, debug=True):
        self.app.run(debug=debug)

if __name__ == '__main__':
    # Create necessary directories
    os.makedirs('static/idols', exist_ok=True)
    os.makedirs('templates', exist_ok=True)
    
    # Create HTML templates
    with open('templates/index.html', 'w') as f:
        f.write('''<!DOCTYPE html>
<html>
<head>
    <title>Ganesh Idols</title>
    <style>
        .idol-container { display: flex; flex-wrap: wrap; gap: 20px; }
        .idol-card { border: 1px solid #ddd; padding: 15px; border-radius: 10px; width: 250px; }
        .idol-img { width: 100%; height: 200px; object-fit: contain; }
        .btn { background-color: #4CAF50; color: white; padding: 10px; text-align: center; 
               border-radius: 5px; text-decoration: none; display: block; margin-top: 10px; }
    </style>
</head>
<body>
    <h1>Divine Ganesh Idols Collection</h1>
    <div class="idol-container">
        {% for idol in idols %}
        <div class="idol-card">
            <img src="{{ idol.image_path }}" class="idol-img">
            <h3>{{ idol.name }}</h3>
            <p>Size: {{ idol.size }}</p>
            <a href="/ar/{{ idol.id }}" class="btn">View in Your Space</a>
        </div>
        {% endfor %}
    </div>
</body>
</html>''')
    
    with open('templates/ar.html', 'w') as f:
        f.write('''<!DOCTYPE html>
<html>
<head>
    <title>AR Experience</title>
    <style>
        #camera-container { position: relative; width: 100%; max-width: 800px; }
        #camera, #preview { width: 100%; border: 2px solid #333; }
        #idol-overlay { position: absolute; max-height: 200px; transform-origin: bottom center; }
        .controls { margin: 15px 0; padding: 10px; background: #f5f5f5; }
        .slider-container { margin: 10px 0; }
        .btn { background: #4CAF50; color: white; border: none; padding: 10px 15px; 
               border-radius: 5px; cursor: pointer; font-size: 16px; margin-right: 10px; }
        #loading { display: none; position: fixed; top: 0; left: 0; width: 100%; 
                  height: 100%; background: rgba(0,0,0,0.5); z-index: 1000; }
        .spinner { position: absolute; top: 50%; left: 50%; transform: translate(-50%, -50%); 
                  color: white; font-size: 24px; }
    </style>
</head>
<body>
    <h1>Try {{ idol.name }} in Your Space</h1>
    
    <div id="camera-container">
        <video id="camera" autoplay playsinline></video>
        <canvas id="preview" style="display:none;"></canvas>
        <img id="idol-overlay" src="/get_idol/{{ idol.id }}">
    </div>
    
    <div class="controls">
        <div class="slider-container">
            <label>Size: <span id="scale-value">30%</span></label>
            <input type="range" id="scale" min="0.1" max="0.5" step="0.05" value="0.3">
        </div>
        <button id="capture-btn" class="btn">Capture Wall</button>
        <button id="process-btn" class="btn" style="display:none;">Generate Divine View</button>
    </div>
    
    <div id="result-container" style="margin-top:20px; display:none;">
        <h2>Your Divine Ganesh</h2>
        <img id="result-image" style="max-width:100%; border:10px solid #d4af37;">
        <button id="print-btn" class="btn">Print Blessing</button>
    </div>
    
    <div id="loading">
        <div class="spinner">Creating your divine experience...</div>
    </div>
    
    <script>
        const video = document.getElementById('camera');
        const canvas = document.getElementById('preview');
        const ctx = canvas.getContext('2d');
        const idolImg = document.getElementById('idol-overlay');
        const scaleSlider = document.getElementById('scale');
        const scaleValue = document.getElementById('scale-value');
        const captureBtn = document.getElementById('capture-btn');
        const processBtn = document.getElementById('process-btn');
        const resultContainer = document.getElementById('result-container');
        const resultImage = document.getElementById('result-image');
        const loading = document.getElementById('loading');
        const printBtn = document.getElementById('print-btn');
        
        let isPositioning = false;
        let currentIdolId = {{ idol.id }};

        // Camera setup
        navigator.mediaDevices.getUserMedia({ video: true })
            .then(stream => {
                video.srcObject = stream;
                video.onloadedmetadata = () => {
                    // Position idol at bottom center initially
                    positionIdol(video.clientWidth/2, video.clientHeight);
                };
            })
            .catch(err => console.error("Camera error: ", err));

        // Idol positioning
        video.addEventListener('click', e => {
            if(!isPositioning) return;
            positionIdol(e.offsetX, e.offsetY);
        });

        // Size adjustment
        scaleSlider.addEventListener('input', () => {
            const scale = parseFloat(scaleSlider.value);
            scaleValue.textContent = `${Math.round(scale * 100)}%`;
            idolImg.style.transform = `scale(${scale})`;
        });

        // Capture button
        captureBtn.addEventListener('click', () => {
            canvas.width = video.videoWidth;
            canvas.height = video.videoHeight;
            ctx.drawImage(video, 0, 0);
            
            video.style.display = 'none';
            canvas.style.display = 'block';
            isPositioning = true;
            processBtn.style.display = 'inline-block';
            captureBtn.textContent = 'Recapture';
        });

        // Process button
        processBtn.addEventListener('click', async () => {
            loading.style.display = 'block';
            
            try {
                // Get position data
                const rect = canvas.getBoundingClientRect();
                const x = parseFloat(idolImg.dataset.x);
                const y = parseFloat(idolImg.dataset.y);
                const scale = parseFloat(scaleSlider.value);
                
                // Prepare form data
                const formData = new FormData();
                formData.append('idol_id', currentIdolId);
                formData.append('x', x);
                formData.append('y', y);
                formData.append('scale', scale);
                
                // Add canvas image
                canvas.toBlob(blob => {
                    formData.append('wall', blob, 'wall.jpg');
                    
                    // Submit to server
                    fetch('/process', {
                        method: 'POST',
                        body: formData
                    })
                    .then(response => {
                        if (!response.ok) {
                            throw new Error('Server error');
                        }
                        return response.json();
                    })
                    .then(data => {
                        if (data.error) {
                            throw new Error(data.error);
                        }
                        
                        // Display result
                        resultImage.src = data.result;
                        resultContainer.style.display = 'block';
                        window.scrollTo({
                            top: document.body.scrollHeight,
                            behavior: 'smooth'
                        });
                    })
                    .catch(error => {
                        alert(`Error: ${error.message}`);
                    })
                    .finally(() => {
                        loading.style.display = 'none';
                    });
                }, 'image/jpeg');
            } catch (error) {
                alert(`Error: ${error.message}`);
                loading.style.display = 'none';
            }
        });

        // Print button
        printBtn.addEventListener('click', () => {
            window.print();
        });

        function positionIdol(x, y) {
            const container = document.getElementById('camera-container');
            const rect = container.getBoundingClientRect();
            
            // Calculate relative position (0-1)
            const relX = (x - rect.left) / rect.width;
            const relY = (y - rect.top) / rect.height;
            
            // Position the overlay
            idolImg.style.left = `${x - idolImg.width/2}px`;
            idolImg.style.top = `${y - idolImg.height}px`;
            
            // Store position data
            idolImg.dataset.x = relX;
            idolImg.dataset.y = relY;
        }
    </script>
</body>
</html>''')
    
    # Create sample idol images
    def create_sample_image(color, path):
        img = np.zeros((400, 300, 3), dtype=np.uint8)
        
        # Body
        cv2.ellipse(img, (150, 250), (100, 150), 0, 0, 180, color, -1)
        
        # Head
        cv2.circle(img, (150, 150), 80, color, -1)
        
        # Ears
        cv2.ellipse(img, (70, 150), (30, 50), 0, 0, 360, color, -1)
        cv2.ellipse(img, (230, 150), (30, 50), 0, 0, 360, color, -1)
        
        # Trunk
        cv2.ellipse(img, (150, 180), (40, 60), 220, 0, 180, color, -1)
        
        # Eyes
        cv2.circle(img, (120, 140), 10, (0, 0, 0), -1)
        cv2.circle(img, (180, 140), 10, (0, 0, 0), -1)
        
        # Save
        cv2.imwrite(path, img)
    
    #create_sample_image((220, 180, 60), 'static/idols/golden.jpg')  # Golden idol
    #create_sample_image((200, 200, 200), 'static/idols/marble.jpg')  # Marble idol
    
    # Run the application
    app = GaneshARApp()
    app.run()