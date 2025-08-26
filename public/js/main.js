
const createUserBtn = document.getElementById("create-user");
const username = document.getElementById("username");
const allusersHtml = document.getElementById("allusers");
const localVideo = document.getElementById("localVideo");
const remoteVideo = document.getElementById("remoteVideo");
const endCallBtn = document.getElementById("end-call-btn");

const socket = io();

// ---- Subtitle inside remoteVideo container ----
let subtitleEl = document.getElementById("subtitle");
if (!subtitleEl) {
  // make sure parent can hold absolute positioned children
  const remoteContainer = remoteVideo.parentElement;
  if (getComputedStyle(remoteContainer).position === "static") {
    remoteContainer.style.position = "relative";
  }

  subtitleEl = document.createElement("div");
  subtitleEl.id = "subtitle";
  subtitleEl.style.position = "absolute";
  subtitleEl.style.left = "50%";
  subtitleEl.style.transform = "translateX(-50%)";
  subtitleEl.style.bottom = "10px";
  subtitleEl.style.background = "rgba(0,0,0,0.6)";
  subtitleEl.style.color = "white";
  subtitleEl.style.padding = "6px 12px";
  subtitleEl.style.borderRadius = "6px";
  subtitleEl.style.fontSize = "18px";
  subtitleEl.style.maxWidth = "90%";
  subtitleEl.style.textAlign = "center";

  remoteContainer.appendChild(subtitleEl);
}
// ---------------------------------------------

socket.on("translation", (payload) => {
  try {
    if (payload.text) {
      subtitleEl.innerText = payload.text;
      clearTimeout(subtitleEl._clearT);
      subtitleEl._clearT = setTimeout(() => { subtitleEl.innerText = ""; }, 4000);
    }

    if (payload.audio_b64) {
      const binary = atob(payload.audio_b64);
      const len = binary.length;
      const bytes = new Uint8Array(len);
      for (let i = 0; i < len; i++) bytes[i] = binary.charCodeAt(i);
      const blob = new Blob([bytes.buffer], { type: "audio/mpeg" });
      const url = URL.createObjectURL(blob);
      const a = new Audio(url);
      a.play().catch((e) => {
        console.warn("Auto-play blocked, user gesture required to play audio", e);
      });
      a.onended = () => URL.revokeObjectURL(url);
    }
  } catch (e) {
    console.error("Error handling translation payload", e);
  }
});

let localStream;
let caller = [];

// Single Method for peer connection
const PeerConnection = (function () {
  let peerConnection;

  const createPeerConnection = () => {
    const config = {
      iceServers: [
        {
          urls: "stun:stun.l.google.com:19302",
        },
      ],
    };
    peerConnection = new RTCPeerConnection(config);

    // add local stream to peer connection
    localStream.getTracks().forEach((track) => {
      peerConnection.addTrack(track, localStream);
    });
    // listen to remote stream and add to peer connection
    peerConnection.ontrack = function (event) {
      remoteVideo.srcObject = event.streams[0];
    };
    // listen for ice candidate
    peerConnection.onicecandidate = function (event) {
      if (event.candidate) {
        socket.emit("icecandidate", event.candidate);
      }
    };

    return peerConnection;
  };

  return {
    getInstance: () => {
      if (!peerConnection) {
        peerConnection = createPeerConnection();
      }
      return peerConnection;
    },
  };
})();

// handle browser events
createUserBtn.addEventListener("click", (e) => {
  if (username.value !== "") {
    const usernameContainer = document.querySelector(".username-input");
    socket.emit("join-user", username.value);
    usernameContainer.style.display = "none";
  }
});
endCallBtn.addEventListener("click", (e) => {
  socket.emit("call-ended", caller);
});

// handle socket events
socket.on("joined", (allusers) => {
  console.log({ allusers });
  const createUsersHtml = () => {
    allusersHtml.innerHTML = "";

    for (const user in allusers) {
      const li = document.createElement("li");
      li.textContent = `${user} ${user === username.value ? "(You)" : ""}`;

      if (user !== username.value) {
        const button = document.createElement("button");
        button.classList.add("call-btn");
        button.addEventListener("click", (e) => {
          startCall(user);
        });
        const img = document.createElement("img");
        img.setAttribute("src", "/images/phone.jpeg");
        img.setAttribute("width", 20);

        button.appendChild(img);

        li.appendChild(button);
      }

      allusersHtml.appendChild(li);
    }
  };

  createUsersHtml();
});
socket.on("offer", async ({ from, to, offer }) => {
  const pc = PeerConnection.getInstance();
  // set remote description
  await pc.setRemoteDescription(offer);
  const answer = await pc.createAnswer();
  await pc.setLocalDescription(answer);
  socket.emit("answer", { from, to, answer: pc.localDescription });
  caller = [from, to];
});
socket.on("answer", async ({ from, to, answer }) => {
  const pc = PeerConnection.getInstance();
  await pc.setRemoteDescription(answer);
  // show end call button
  endCallBtn.style.display = "block";
  // socket.emit("end-call", { from, to });
  caller = [from, to];
});
socket.on("icecandidate", async (candidate) => {
  console.log({ candidate });
  const pc = PeerConnection.getInstance();
  await pc.addIceCandidate(new RTCIceCandidate(candidate));
});
socket.on("end-call", ({ from, to }) => {
  endCallBtn.style.display = "block";
});
socket.on("call-ended", (caller) => {
  endCall();
});

// start call method
const startCall = async (user) => {
  console.log({ user });
  const pc = PeerConnection.getInstance();
  const offer = await pc.createOffer();
  console.log({ offer });
  await pc.setLocalDescription(offer);
  socket.emit("offer", {
    from: username.value,
    to: user,
    offer: pc.localDescription,
  });
};

const endCall = () => {
  const pc = PeerConnection.getInstance();
  if (pc) {
    pc.close();
    endCallBtn.style.display = "none";
  }
};

document.getElementById("setLangBtn").addEventListener("click", () => {
  const src = document.getElementById("srcLang").value;
  const tgt = document.getElementById("tgtLang").value;
  socket.emit("set-langs", { src, tgt });
});



// initialize app
const startMyVideo = async () => {
  try {
    const stream = await navigator.mediaDevices.getUserMedia({
      audio: true,
      video: true,
    });
    console.log({ stream });
    localStream = stream;
    localVideo.srcObject = stream;
  } catch (error) {}
};

(() => {
  async function startLocalPreview() {
    const videoEl = document.getElementById('localVideo');
    if (!videoEl) return;

    if (!window.isSecureContext) {
      console.warn('getUserMedia requires HTTPS or localhost. Current context is not secure.');
    }

    try {
      // If already set by other logic, don’t reinitialize
      if (videoEl.srcObject instanceof MediaStream && videoEl.srcObject.getVideoTracks().length) {
        return;
      }

      const constraints = {
        video: {
          width: { ideal: 1280 },
          height: { ideal: 720 },
          facingMode: 'user'
        },
        audio: false
      };

      const stream = await navigator.mediaDevices.getUserMedia(constraints);
      videoEl.srcObject = stream;

      // Some browsers need an explicit play call
      const playPromise = videoEl.play?.();
      if (playPromise && typeof playPromise.then === 'function') {
        await playPromise.catch(() => {/* ignore autoplay race */});
      }

      console.log('Local preview started');
    } catch (err) {
      console.error('Failed to start local preview:', err);
      // Optional: show a user-friendly message somewhere in the UI
      // document.getElementById('camera-status').textContent = 'Camera blocked or unavailable';
    }
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', startLocalPreview, { once: true });
  } else {
    startLocalPreview();
  }
})();
"use strict";
/**
 * Make .local-video draggable within the main container only.
 * - Constrains movement inside .main-container
 * - Uses absolute positioning relative to .main-container
 * - Clamps within container with a small margin
 * - Saves/restores position relative to container
 */
(function () {
  const pip = document.querySelector(".local-video");
  const container =
    document.querySelector(".main-container") || (pip ? pip.parentElement : null);
  if (!pip || !container) return;

  const STORAGE_KEY = "local-video-position-main-container";
  const MARGIN = 8; // min gap from edges

  // Ensure the container can anchor absolutely positioned children
  if (getComputedStyle(container).position === "static") {
    container.style.position = "relative";
  }

  let dragging = false;
  let startX = 0;
  let startY = 0;
  let elStartLeft = 0;
  let elStartTop = 0;
  let capturedPointerId = null;

  // Ensure absolute positioning relative to the container and preserve visual position
  function ensureAbsoluteFromCurrentRect() {
    const style = getComputedStyle(pip);
    const pipRect = pip.getBoundingClientRect();
    const containerRect = container.getBoundingClientRect();

    if (style.position !== "absolute" || pip.parentElement !== container) {
      // Compute current position relative to the container
      const left = Math.round(pipRect.left - containerRect.left);
      const top = Math.round(pipRect.top - containerRect.top);

      if (pip.parentElement !== container) {
        container.appendChild(pip);
      }

      pip.style.position = "absolute";
      pip.style.left = left + "px";
      pip.style.top = top + "px";
      pip.style.right = "auto";
      pip.style.bottom = "auto";
      pip.style.margin = "0";
      pip.style.transform = "none";
      pip.style.zIndex = "1000";
    }
  }

  // Clamp within container
  function clamp(n, min, max) {
    return Math.max(min, Math.min(n, max));
  }

  // Apply position relative to container
  function applyPos(left, top) {
    const w = pip.offsetWidth;
    const h = pip.offsetHeight;

    // Use clientWidth/Height to avoid scrollbars
    const cw = container.clientWidth;
    const ch = container.clientHeight;

    let maxLeft = cw - w - MARGIN;
    let maxTop = ch - h - MARGIN;

    // Guard for small containers
    maxLeft = Math.max(MARGIN, maxLeft);
    maxTop = Math.max(MARGIN, maxTop);

    pip.style.left = clamp(left, MARGIN, maxLeft) + "px";
    pip.style.top = clamp(top, MARGIN, maxTop) + "px";
    pip.style.right = "auto";
    pip.style.bottom = "auto";
  }

  function savePos() {
    const left = parseFloat(pip.style.left || "0");
    const top = parseFloat(pip.style.top || "0");
    try {
      localStorage.setItem(
        STORAGE_KEY,
        JSON.stringify({ left: Math.round(left), top: Math.round(top) })
      );
    } catch {}
  }

  function restorePos() {
    try {
      const saved = JSON.parse(localStorage.getItem(STORAGE_KEY) || "null");
      ensureAbsoluteFromCurrentRect();
      if (saved && Number.isFinite(saved.left) && Number.isFinite(saved.top)) {
        applyPos(saved.left, saved.top);
      } else {
        // If no saved pos, keep current visual spot but normalize to explicit left/top
        const pipRect = pip.getBoundingClientRect();
        const containerRect = container.getBoundingClientRect();
        const left = pipRect.left - containerRect.left;
        const top = pipRect.top - containerRect.top;
        applyPos(left, top);
      }
    } catch {
      ensureAbsoluteFromCurrentRect();
    }
  }

  function onPointerDown(e) {
    // Only primary mouse button (or touch)
    if (e.button !== undefined && e.button !== 0) return;

    e.preventDefault(); // prevent scroll on touch
    dragging = true;
    pip.classList.add("is-dragging");

    ensureAbsoluteFromCurrentRect();

    const pipRect = pip.getBoundingClientRect();
    const containerRect = container.getBoundingClientRect();

    startX = e.clientX;
    startY = e.clientY;
    elStartLeft = pipRect.left - containerRect.left;
    elStartTop = pipRect.top - containerRect.top;

    try {
      pip.setPointerCapture(e.pointerId);
      capturedPointerId = e.pointerId;
    } catch {}

    window.addEventListener("pointermove", onPointerMove, { passive: true });
    window.addEventListener("pointerup", onPointerUp, { once: true });
    window.addEventListener("pointercancel", onPointerUp, { once: true });
  }

  function onPointerMove(e) {
    if (!dragging) return;
    const dx = e.clientX - startX;
    const dy = e.clientY - startY;
    applyPos(elStartLeft + dx, elStartTop + dy);
  }

  function onPointerUp() {
    if (!dragging) return;
    dragging = false;
    pip.classList.remove("is-dragging");
    savePos();
    window.removeEventListener("pointermove", onPointerMove);
    try {
      if (capturedPointerId != null) pip.releasePointerCapture(capturedPointerId);
    } catch {}
    capturedPointerId = null;
  }

  // Keep inside container on viewport/container resize
  const reClamp = () => {
    const left = parseFloat(pip.style.left || "0");
    const top = parseFloat(pip.style.top || "0");
    applyPos(left, top);
  };
  window.addEventListener("resize", reClamp);
  if (typeof ResizeObserver !== "undefined") {
    const ro = new ResizeObserver(reClamp);
    ro.observe(container);
  }

  // Improve UX on mobile
  pip.style.userSelect = "none";
  pip.style.touchAction = "none";

  // If you click on the <video>, we still want to drag → disable video pointer handling
  const vid = pip.querySelector("video");
  if (vid) vid.style.pointerEvents = "none";

  // Init
  restorePos();
  pip.addEventListener("pointerdown", onPointerDown);
})();

startMyVideo();
