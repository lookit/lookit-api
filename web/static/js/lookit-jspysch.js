const origInitJsPsych = initJsPsych;

initJsPsych = function (options) {
    const jsPsych = origInitJsPsych(options);
    const origJsPsychRun = jsPsych.run;

    jsPsych.run = async function (timeline) {
        // check timeline here...
        console.log(timeline);
        return origJsPsychRun(timeline);
    }

    return jsPsych;
}
