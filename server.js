import express from "express";
import { createServer } from "http";
import { Server } from "socket.io";
import { fileURLToPath } from "url";
import { dirname, join } from "path";
import { WebSocketServer } from "ws"; // NEW: For Python connection

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
  console.log(`Someone connected to socket server and socket id is ${socket.id}`);
  socket.on("join-user", (username) => {
    console.log(`${username} joined socket connection`);
    allusers[username] = { username, id: socket.id };
    io.emit("joined", allusers);
  });

  socket.on("offer", ({ from, to, offer }) => {
    console.log({ from, to, offer });
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
    console.log({ candidate });
    socket.broadcast.emit("icecandidate", candidate);
  });
});

// -----------------
// NEW: WebSocket for Python connection
// -----------------
const wss = new WebSocketServer({ server });


wss.on("connection", (ws) => {
  console.log("Python connected to WebSocket");

  ws.on("message", (message) => {
    try {
      const data = JSON.parse(message.toString());
      console.log("From Python:", data);
      // broadcast parsed object to browsers
      io.emit("translation", data);
    } catch (err) {
      console.error("Invalid JSON from Python:", err);
    }
  });

  ws.on("close", () => {
    console.log("Python disconnected");
  });
});

// -----------------

const PORT = process.env.PORT || 9000;
server.listen(PORT, () => {
  console.log(`Server listening on port ${PORT}`);
});


