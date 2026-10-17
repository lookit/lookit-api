document.addEventListener("DOMContentLoaded", async () => {
    const pubDiv = document.getElementById("zotero-publication-list");

    // Use "format=json" and "include=bib" instead of "format=bib", because the latter doesn't allow sorting by date.
    // The API returns at most 100 items per request, so page through the results with "start".
    // https://www.zotero.org/support/dev/web_api/v3/basics
    const pageSize = 100;
    const baseUrl = `https://api.zotero.org/groups/5819486/items?format=json&include=bib&linkwrap=1&style=apa&sort=date&direction=desc&v=3&itemType=-attachment&limit=${pageSize}`;

    try {
        let bibs = "";
        let start = 0;
        while (true) {
            const response = await fetch(`${baseUrl}&start=${start}`);
            if (!response.ok) {
                throw new Error(`Response status: ${response.status}`);
            }
            const items = await response.json();
            items.forEach((item) => {
                bibs += item.bib;
            });
            if (items.length < pageSize) {
                break;
            }
            start += pageSize;
        }
        pubDiv.innerHTML = bibs;
    } catch (error) {
        console.error(error.message);
        pubDiv.innerHTML = `<p class="text-danger">Something went wrong retrieving the publications. Please try again later.</p>`;
    }
});