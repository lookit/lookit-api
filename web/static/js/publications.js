// Tags and attributes that Zotero's CSL bibliography HTML uses. Everything else is stripped.
const ALLOWED_TAGS = new Set(["DIV", "SPAN", "I", "EM", "B", "STRONG", "SUP", "SUB", "A", "BR"]);
const ALLOWED_ATTRS = { A: ["href"], DIV: ["class"], SPAN: ["class"] };
// Disallowed elements whose contents should also be dropped, rather than kept as text.
const DROPPED_TAGS = new Set(["SCRIPT", "STYLE", "TEMPLATE", "NOSCRIPT", "IFRAME", "OBJECT", "SVG", "MATH"]);

// Copy only allowed elements/attributes from an inert parsed node into the live document.
const sanitizeNode = (node) => {
    if (node.nodeType === Node.TEXT_NODE) {
        return document.createTextNode(node.textContent);
    }
    if (node.nodeType !== Node.ELEMENT_NODE || DROPPED_TAGS.has(node.tagName.toUpperCase())) {
        return null;
    }
    const children = Array.from(node.childNodes).map(sanitizeNode).filter(Boolean);
    if (!ALLOWED_TAGS.has(node.tagName)) {
        // Drop the element itself but keep its (sanitized) contents.
        const fragment = document.createDocumentFragment();
        fragment.append(...children);
        return fragment;
    }
    const el = document.createElement(node.tagName);
    (ALLOWED_ATTRS[node.tagName] || []).forEach((attr) => {
        const value = node.getAttribute(attr);
        if (value !== null) {
            el.setAttribute(attr, value);
        }
    });
    if (el.tagName === "A") {
        let url = null;
        try {
            url = new URL(el.getAttribute("href"), window.location.href);
        } catch (e) {
            // invalid URL; handled below
        }
        if (url && (url.protocol === "https:" || url.protocol === "http:")) {
            el.setAttribute("href", url.href);
            el.setAttribute("target", "_blank");
            el.setAttribute("rel", "noopener noreferrer");
        } else {
            el.removeAttribute("href");
        }
    }
    el.append(...children);
    return el;
};

const sanitizeHtml = (html) => {
    // DOMParser documents are inert: scripts don't run and event handlers don't fire.
    const parsed = new DOMParser().parseFromString(html, "text/html");
    const fragment = document.createDocumentFragment();
    Array.from(parsed.body.childNodes).map(sanitizeNode).filter(Boolean).forEach((node) => fragment.append(node));
    return fragment;
};

document.addEventListener("DOMContentLoaded", async () => {
    const pubDiv = document.getElementById("zotero-publication-list");

    // Use "format=json" and "include=bib" instead of "format=bib", because the latter doesn't allow sorting by date.
    // Use "/items/top" so that child notes and attachments aren't returned as separate entries.
    // The API returns at most 100 items per request, so fetch the first page, then use the Total-Results header
    // to request the remaining pages in parallel.
    // https://www.zotero.org/support/dev/web_api/v3/basics
    const pageSize = 100;
    const baseUrl = `https://api.zotero.org/groups/5819486/items/top?format=json&include=bib&linkwrap=1&style=apa&sort=date&direction=desc&v=3&itemType=-attachment&limit=${pageSize}`;

    const fetchPage = async (start) => {
        const response = await fetch(`${baseUrl}&start=${start}`);
        if (!response.ok) {
            throw new Error(`Response status: ${response.status}`);
        }
        return response;
    };

    try {
        const firstResponse = await fetchPage(0);
        const totalResults = parseInt(firstResponse.headers.get("Total-Results"), 10) || 0;
        const remainingStarts = [];
        for (let start = pageSize; start < totalResults; start += pageSize) {
            remainingStarts.push(start);
        }
        const pages = await Promise.all([
            firstResponse.json(),
            ...remainingStarts.map(async (start) => (await fetchPage(start)).json()),
        ]);
        const bibs = pages.flat().map((item) => item.bib || "").join("");
        pubDiv.replaceChildren(sanitizeHtml(bibs));
    } catch (error) {
        console.error(error.message);
        pubDiv.innerHTML = `<p class="text-danger">Something went wrong retrieving the publications. Please try again later.</p>`;
    }
});
