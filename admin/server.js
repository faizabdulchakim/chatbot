const express = require('express');
const path = require('path');
const multer = require('multer');
const fs = require('fs');
const XLSX = require('xlsx');
const app = express();

// Setup multer for file uploads
const upload = multer({ 
    dest: path.join(__dirname, 'uploads'),
    limits: { fileSize: 10 * 1024 * 1024 } // 10MB limit for Excel
});

app.use(express.json());
app.use(express.static(__dirname));

// Ensure uploads directory exists
if (!fs.existsSync(path.join(__dirname, 'uploads'))) {
    fs.mkdirSync(path.join(__dirname, 'uploads'));
}

// Serve the admin page
app.get('/', (req, res) => {
    res.sendFile(path.join(__dirname, 'index.html'));
});

// API Proxy endpoints
const API_URL = 'http://127.0.0.1:8001';

app.get('/api/documents', async (req, res) => {
    try {
        const response = await fetch(`${API_URL}/documents`);
        const data = await response.json();
        res.json(data);
    } catch (error) {
        res.status(500).json({ error: error.message });
    }
});

app.post('/api/documents', async (req, res) => {
    try {
        const response = await fetch(`${API_URL}/documents`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(req.body)
        });
        const data = await response.json();
        res.json(data);
    } catch (error) {
        res.status(500).json({ error: error.message });
    }
});

app.delete('/api/documents/:id', async (req, res) => {
    try {
        const response = await fetch(`${API_URL}/documents/${req.params.id}`, {
            method: 'DELETE'
        });
        const data = await response.json();
        res.json(data);
    } catch (error) {
        res.status(500).json({ error: error.message });
    }
});

// File upload endpoint
app.post('/api/upload', upload.single('file'), async (req, res) => {
    try {
        if (!req.file) {
            return res.status(400).json({ error: 'No file uploaded' });
        }
        
        const docId = req.body.docId || `file-${Date.now()}`;
        const source = req.body.source || 'file-upload';
        const filePath = req.file.path;
        const originalFilename = req.file.originalname;
        
        let content = '';
        
        // Check file extension and process accordingly
        const fileExt = path.extname(originalFilename).toLowerCase();
        
        if (fileExt === '.xlsx' || fileExt === '.xls') {
            // Process Excel file
            const workbook = XLSX.readFile(filePath);
            const sheetNames = workbook.SheetNames;
            
            // Read all sheets
            for (const sheetName of sheetNames) {
                const sheet = workbook.Sheets[sheetName];
                const jsonData = XLSX.utils.sheet_to_json(sheet, { header: 1 });
                
                content += `=== Sheet: ${sheetName} ===\n\n`;
                
                // Convert rows to readable format
                jsonData.forEach((row, rowIndex) => {
                    if (row && row.length > 0) {
                        content += `Row ${rowIndex + 1}: ${row.join(' | ')}\n`;
                    }
                });
                
                content += '\n\n';
            }
        } else {
            // Process text-based files
            content = fs.readFileSync(filePath, 'utf8');
        }
        
        // Clean up uploaded file
        fs.unlinkSync(filePath);
        
        // Send to Chatbot API
        const response = await fetch(`${API_URL}/documents`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                id: docId,
                content: content,
                source: source,
                metadata: {
                    originalFilename: originalFilename,
                    uploadedAt: new Date().toISOString(),
                    fileType: fileExt
                }
            })
        });
        
        const result = await response.json();
        
        if (response.ok) {
            res.json({ 
                success: true, 
                message: `File uploaded and processed successfully (${sheetNames ? sheetNames.length + ' sheets' : 'text file'})`,
                document: result 
            });
        } else {
            res.status(response.status).json(result);
        }
    } catch (error) {
        // Clean up file on error
        if (req.file && fs.existsSync(req.file.path)) {
            fs.unlinkSync(req.file.path);
        }
        res.status(500).json({ error: error.message });
    }
});

const PORT = 3003;
app.listen(PORT, '0.0.0.0', () => {
    console.log(`Document Admin UI running at http://0.0.0.0:${PORT}`);
});
