const origInitJsPsych = initJsPsych;

function csrfToken() {
    /**
     * Function to get csrf token from cookies. 
     */
    return document.cookie
        .split("; ")
        .find((row) => row.startsWith("csrftoken="))
        ?.split("=")[1];
}

async function get(url) {
    /**
     * Function for REST get.
     */
    const request = new Request(
        url,
        {
            method: 'GET',
            mode: 'same-origin' // Do not send CSRF token to another domain.
        }
    );

    const response = await fetch(request);
    return await response.json();
}


async function patch(url, data) {
    /**
     * Function for REST patch.  
     */
    const request = new Request(
        url,
        {
            method: 'PATCH',
            headers: {
                'X-CSRFToken': csrfToken(),
                'Content-Type': 'application/vnd.api+json'
            },
            mode: 'same-origin', // Do not send CSRF token to another domain.
            body: JSON.stringify({ data })
        }
    );

    const response = await fetch(request);
    return await response.json();
}

function on_data_update(url, id, userFunc) {
    /**
     * Function that returns a function to be used in place of jsPsych's option 
     * "on_data_update".  "userFunc" should be the user's implementation of 
     * "on_data_update".  Since this is the data that is returned from each 
     * trial, this function will get the collected trial data and append the 
     * current data point.
     */
    return async function (data) {
        const { data: { attributes: { exp_data } } } = await get(url);

        await patch(url, {
            id, type: "responses", attributes: {
                exp_data: [...exp_data, data]
            }
        });

        // Don't call the function if not defined by user.
        if (typeof userFunc === 'function') {
            userFunc(data)
        };
    }
}


function on_finish(url, id, userFunc) {
    /**
     * Function that returns a function to be used in place of jsPsych's option 
     * "on_finish".  "userFunc" should be the user's implementation of 
     * "on_finish".  Since this is point where the experiment has ended, the 
     * function wil set completed to true and overwrites all experiment data 
     * with the full set of collected data.
     */
    return async function (data) {
        await patch(url, {
            id, type: "responses", attributes: {
                exp_data: data.trials,
                completed: true
            }
        });

        // Don't call the function if not defined by user.
        if (typeof userFunc === 'function') {
            userFunc(data);
        };
    }
}

export default function (url, responseUuid) {
    /**
     * Function that returns a function to replace jsPysch's initJsPsych.
     */
    return function (opts) {
        const jsPsych = origInitJsPsych({
            ...opts,
            on_data_update: on_data_update(url, responseUuid, opts.on_data_update),
            on_finish: on_finish(url, responseUuid, opts.on_finish)
        });
        const origJsPsychRun = jsPsych.run;

        jsPsych.run = async function (timeline) {
            // check timeline here...
            return origJsPsychRun(timeline);
        }

        return jsPsych;
    }
}
