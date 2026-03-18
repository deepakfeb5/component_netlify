function downloadResultsCSV() {
    const bom = window.bomData || [];

    fetch("/download_results_csv", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ bom })
    })
        .then(res => res.blob())
        .then(blob => {
            const url = window.URL.createObjectURL(blob);
            const a = document.createElement("a");
            a.href = url;
            a.download = "BOM_Results.csv";
            a.click();
        });
}
