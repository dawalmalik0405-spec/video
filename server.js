import express from "express";
import { createServer } from "http";
import { Server } from "socket.io";
import { fileURLToPath } from "url";
import { dirname, join } from "path";
import { WebSocketServer } from "ws";
import { spawn } from "child_process";

const app = express();
const server = createServer(app);
const io = new Server(server);
const allusers = {};

const __dirname = dirname(fileURLToPath(import.meta.url));
app.use(express.static(join(__dirname, "public")));

app.get("/", (req, res) => {
  console.log("GET Request /");
  res.sendFile(join(__dirname, "app", "index.html"));
});

io.on("connection", (socket) => {
  console.log(`Someone connected: ${socket.id}`);
  socket.on("join-user", (username) => {
    allusers[username] = { username, id: socket.id };
    io.emit("joined", allusers);
  });
  socket.on("offer", ({ from, to, offer }) => {
    io.to(allusers[to].id).emit("offer", { from, to, offer });
  });
  socket.on("answer", ({ from, to, answer }) => {
    io.to(allusers[from].id).emit("answer", { from, to, answer });
  });
  socket.on("end-call", ({ from, to }) => {
    io.to(allusers[to].id).emit("end-call", { from, to });
  });
  socket.on("call-ended", (caller) => {
    const [from, to] = caller;
    io.to(allusers[from].id).emit("call-ended", caller);
    io.to(allusers[to].id).emit("call-ended", caller);
  });
  socket.on("icecandidate", (candidate) => {
    socket.broadcast.emit("icecandidate", candidate);
  });
});

// WebSocket for Python
const wss = new WebSocketServer({ server });
wss.on("connection", (ws) => {
  console.log("Python connected to WebSocket");

  ws.on("message", (message) => {
    try {
      const data = JSON.parse(message.toString());
      io.emit("translation", data);
    } catch (err) {
      console.error("Invalid JSON from Python:", err);
    }
  });

  ws.on("close", (code, reason) => {
    // Sanitize code if invalid
    if ((code < 1000 || code > 1015) && (code < 3000 || code > 4999)) {
      console.warn(`⚠️ Received invalid close code from client: ${code} — treating as 1000`);
      code = 1000;
      reason = "Normal Closure (forced)";
    }
    console.log(`Python disconnected with code ${code}, reason: ${reason}`);
  });

  ws.on("error", (err) => {
    console.error("WebSocket error:", err);
  });
});


// Start Python translator script
const pythonProcess = spawn("python3", ["translator.py"], {
  cwd: __dirname,
  env: {
    ...process.env,
    WS_URL: "ws://localhost:" + (process.env.PORT || 9000)
  }
});

pythonProcess.stdout.on("data", (data) => {
  console.log(`[Python] ${data}`);
});
pythonProcess.stderr.on("data", (data) => {
  console.error(`[Python Error] ${data}`);
});
pythonProcess.on("close", (code) => {
  console.log(`[Python] exited with code ${code}`);
});

const PORT = process.env.PORT || 9000;
server.listen(PORT, () => {
  console.log(`Server listening on port ${PORT}`);
});


