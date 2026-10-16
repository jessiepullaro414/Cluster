package com.jessiescars.cluster;

import java.net.DatagramPacket;
import java.net.DatagramSocket;
import java.net.InetAddress;
import java.nio.charset.StandardCharsets;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.atomic.AtomicReference;

/**
 * Sends the latest telemetry line (core/Telemetry) to the development PC over UDP, off the main
 * thread. Latest wins: if the network is slow only the newest line is sent. The Android emulator
 * reaches the host's loopback at 10.0.2.2.
 */
final class TelemetryPublisher {
    static final String DEFAULT_HOST = "10.0.2.2";
    static final int DEFAULT_PORT = 5005;

    private final ExecutorService io = Executors.newSingleThreadExecutor();
    private final AtomicReference<String> latest = new AtomicReference<>();
    private volatile String host = DEFAULT_HOST;
    private volatile int port = DEFAULT_PORT;
    private volatile boolean enabled = true;
    private DatagramSocket socket;
    private InetAddress address;
    private String resolvedHost;

    /** "off", or "host" or "host:port". */
    void configure(String spec) {
        if (spec == null) return;
        spec = spec.trim();
        if (spec.equalsIgnoreCase("off")) { enabled = false; return; }
        enabled = true;
        int colon = spec.lastIndexOf(':');
        try {
            if (colon > 0) { host = spec.substring(0, colon); port = Integer.parseInt(spec.substring(colon + 1)); }
            else { host = spec; port = DEFAULT_PORT; }
        } catch (NumberFormatException e) {
            host = DEFAULT_HOST; port = DEFAULT_PORT;
        }
    }

    void publish(String line) {
        if (!enabled) return;
        if (latest.getAndSet(line) != null) return;          // a send is already queued; it will take the newest
        io.execute(this::sendLatest);
    }

    private void sendLatest() {
        String line = latest.getAndSet(null);
        if (line == null) return;
        try {
            if (socket == null) socket = new DatagramSocket();
            String h = host;
            if (address == null || !h.equals(resolvedHost)) { address = InetAddress.getByName(h); resolvedHost = h; }
            byte[] b = line.getBytes(StandardCharsets.US_ASCII);
            socket.send(new DatagramPacket(b, b.length, address, port));
        } catch (Exception e) {
            address = null;                                    // retry name resolution next time; the feed is best effort
        }
    }

    void close() {
        io.shutdownNow();
        if (socket != null) socket.close();
    }
}
