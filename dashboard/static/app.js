(() => {
  const $ = (id) => document.getElementById(id);

  const els = {
    speed: $("speed"),
    gear: $("gear"),
    gearSrc: $("gear-src"),
    rpm: $("rpm"),
    throttle: $("throttle"),
    turnL: $("turn-l"),
    turnR: $("turn-r"),
    brake: $("brake"),
    steerAngle: $("steer-angle"),
    steerNeedle: $("steer-needle"),
    steerRate: $("steer-rate"),
    wfl: $("wfl"),
    wfr: $("wfr"),
    wrl: $("wrl"),
    wrr: $("wrr"),
    iface: $("iface"),
    fps: $("fps"),
    age: $("age"),
    chk: $("chk"),
    conn: $("conn"),
    msgAges: $("msg-ages"),
  };

  const WATCH = ["WHL_SPD", "SAS", "TCS13", "EMS11", "EMS12", "EMS16", "TCU11", "TCU12", "LVR11", "LVR12", "CGW1"];

  function fmt(n, digits = 0) {
    if (n === null || n === undefined || Number.isNaN(n)) return "—";
    return Number(n).toFixed(digits);
  }

  function setOn(el, on) {
    el.classList.toggle("on", !!on);
    el.classList.toggle("off", !on);
  }

  function update(payload) {
    const v = payload.vehicle || {};
    const h = payload.health || {};

    els.speed.textContent = fmt(v.speed_kmh, 0);
    els.gear.textContent = v.gear ?? (v.gear_raw != null ? `RAW:${v.gear_raw}` : "—");
    els.gearSrc.textContent = v.gear_source ? `(${v.gear_source})` : "";
    els.rpm.textContent = v.rpm == null ? "—" : fmt(v.rpm, 0);
    els.throttle.textContent =
      v.throttle_pct == null ? "—" : `${fmt(v.throttle_pct, 0)}%`;

    setOn(els.turnL, v.turn_left);
    setOn(els.turnR, v.turn_right);
    // Pedal only (DriverOverride==2) — not brake_light, which can stay lit
    setOn(els.brake, v.driver_braking);

    const angle = v.steering_angle_deg;
    els.steerAngle.textContent = fmt(angle, 1);
    els.steerRate.textContent = fmt(v.steering_rate_deg_s, 0);

    // Map ±540° to 5%–95% of track width
    const clamped = Math.max(-540, Math.min(540, angle ?? 0));
    const pct = 50 + (clamped / 540) * 45;
    els.steerNeedle.style.left = `${pct}%`;

    els.wfl.textContent = fmt(v.wheel_fl_kmh, 1);
    els.wfr.textContent = fmt(v.wheel_fr_kmh, 1);
    els.wrl.textContent = fmt(v.wheel_rl_kmh, 1);
    els.wrr.textContent = fmt(v.wheel_rr_kmh, 1);

    els.iface.textContent = h.interface || "—";
    els.fps.textContent = fmt(h.frames_per_sec, 0);
    els.age.textContent =
      h.last_frame_age_s == null ? "—" : `${fmt(h.last_frame_age_s, 2)}s`;
    els.chk.textContent = String(h.checksum_errors ?? 0);

    const online = !!h.connected && (h.last_frame_age_s == null || h.last_frame_age_s < 2);
    els.conn.textContent = online ? "LIVE" : "OFFLINE";
    els.conn.classList.toggle("online", online);
    els.conn.classList.toggle("offline", !online);

    const ages = h.msg_age_s || {};
    els.msgAges.innerHTML = WATCH.map((name) => {
      const a = ages[name];
      const miss = a === null || a === undefined || a > 2;
      const label = miss ? "miss" : `${Number(a).toFixed(1)}s`;
      return `<span class="${miss ? "miss" : "ok"}">${name} ${label}</span>`;
    }).join("");
  }

  function connect() {
    const proto = location.protocol === "https:" ? "wss" : "ws";
    const ws = new WebSocket(`${proto}://${location.host}/ws`);

    ws.onmessage = (ev) => {
      try {
        update(JSON.parse(ev.data));
      } catch (_) {
        /* ignore bad frames */
      }
    };

    ws.onclose = () => {
      els.conn.textContent = "OFFLINE";
      els.conn.classList.add("offline");
      els.conn.classList.remove("online");
      setTimeout(connect, 1000);
    };

    ws.onerror = () => {
      ws.close();
    };
  }

  connect();
})();
