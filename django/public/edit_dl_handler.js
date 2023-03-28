const dl = document.getElementById('id_drivers_licence');
dl.addEventListener('input', (event) => {
    const edit = document.getElementById('edit_drivers_licence');
    const regex = /^[A-Z0-9]*$/;
    if (dl.value.length < 7 || !regex.test(dl.value)) {
        edit.disabled = true;
    } else {
        edit.disabled = false;
    }
})