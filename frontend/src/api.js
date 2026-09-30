
// Provides frontend helper functions for communicating with the backend API.
// The API server (uvicorn, http://127.0.0.1:8000) is IPv4-only. Using
// 127.0.0.1 instead of "localhost" avoids Windows resolving localhost to the
// IPv6 loopback (::1) where nothing is listening.
const API = "http://127.0.0.1:8000";

// If the server answers, read its body as JSON. If the body is not JSON
// (empty, HTML error page, proxy message...) fall back to a readable error.
async function parseResponse(response) {
    let data;
    try {
        data = await response.json();
    } catch {
        data = {
            detail: `Server answered with ${response.status} (${response.statusText || "no message"}).`,
        };
    }
    return { ok: response.ok, status: response.status, data };
}

// Turn a failed/never-completed fetch (backend down, CORS blocked, DNS, ...)
// into the same { ok, status, data } shape so callers never see a throw.
function networkError(error) {
    return {
        ok: false,
        status: 0,
        data: {
            detail: `Cannot reach the backend at ${API}. Is the API server running? (${error.message})`,
        },
    };
}

export async function uploadFile(file) {
    // Package the selected file as multipart form data for the upload endpoint.
    const form = new FormData();
    form.append("file", file);
    // Send the file and return the response status together with its JSON data.
    try {
        const response = await fetch(`${API}/upload`, { method: "POST", body: form });
        return await parseResponse(response);
    } catch (error) {
        return networkError(error);
    }
}

export async function ask(question) {
    // Send a user's question as JSON to the backend ask endpoint.
    try {
        const response = await fetch(`${API}/ask`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ question }),
        });
        return await parseResponse(response);
    } catch (error) {
        return networkError(error);
    }
}

// Lightweight "is the backend up" probe used on page load.
export async function health() {
    try {
        const response = await fetch(`${API}/health`);
        return await parseResponse(response);
    } catch (error) {
        return networkError(error);
    }
}
// Return files the backend indexes, newest file, so the Uplaoded files panel show full history
export async function listUploads() {
    try {
        const response = await fetch(`${API}/uploads`);
        return await parseResponse(response);
    } catch (error) {
        return networkError(error);
    }
}

// Delete one uploaded file. The backend removes its indexed chunks, its row in
// the upload log, and the saved copy on disk, so the whole app forgets it.
export async function deleteUpload(filename, fileType) {
    // file_type narrows the request to a single upload when the same name was
    // saved as both a PDF and a DOCX.
    const query = fileType ? `?file_type=${encodeURIComponent(fileType)}` : "";
    try {
        const response = await fetch(
            `${API}/uploads/${encodeURIComponent(filename)}${query}`,
            { method: "DELETE" },
        );
        return await parseResponse(response);
    } catch (error) {
        return networkError(error);
    }
}