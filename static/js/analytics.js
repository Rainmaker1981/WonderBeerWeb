document.addEventListener("DOMContentLoaded", () => {
  const styles = profile.styles || {};
  const sLabels = Object.keys(styles);
  const sData = Object.values(styles);

  const ctx1 = document.getElementById("stylesChart").getContext("2d");
  new Chart(ctx1, {
    type: "bar",
    data: {
      labels: sLabels,
      datasets: [{
        label: "Preference",
        data: sData
      }]
    },
    options: {
      responsive: true,
      scales: {
        y: { beginAtZero: true, ticks: { stepSize: 1 } }
      }
    }
  });

  const flavors = profile.flavors || {};
  const fLabels = Object.keys(flavors);
  const fData = Object.values(flavors);

  const ctx2 = document.getElementById("flavorsChart").getContext("2d");
  new Chart(ctx2, {
    type: "radar",
    data: {
      labels: fLabels,
      datasets: [{
        label: "Flavor Balance",
        data: fData
      }]
    },
    options: {
      responsive: true,
      scales: { r: { beginAtZero: true, ticks: { stepSize: 1 } } }
    }
  });
});
