const express = require('express');
const path = require('path');
const app = express();

// Serve the Chatbot UI
app.get('/', (req, res) => {
    res.sendFile(path.join(__dirname, 'index.html'));
});

// Start the server
const PORT = 3001;
app.listen(PORT, '0.0.0.0', () => {
    console.log(`Chatbot UI is running at http://0.0.0.0:${PORT}`);
});
