// Main process for the application


// Select Originals to Process 
$('#process_selectfolder_btn').click(function(){
	selectFolder('init', '', '');
});

function selectFolder(action, current_path, folder_name) {
	$('#process_welcome_row').hide();
	if (action == '' || action == 'init') {
		var action = 'init';
		var current_path = '';
		var folder_name = '';
	};
	var senddata = { 
		'action' : action,
		'folder_name' : folder_name,
		'current_path' : current_path
	};
	$('#process_working_row').load('/selectfolder', senddata).fadeIn(500);
};

// Select Originals to Process 
$('#process_importfolder_btn').click(function(){
	importFolder('range', '');
});

function importFolder(action, imports_folder) {
	$('#process_welcome_row').hide();
	start_date = '';
	end_date = '';
	if (action == 'analyze') { 
		start_date = document.getElementById('start_date').value;
		end_date = document.getElementById('end_date').value;
	}
	var senddata = { 
		'action' : action,
		'import_folder' : imports_folder,
		'start_date' : start_date,
		'end_date' : end_date
	}; 
	$('#process_working_row').load('/importfolder', senddata).fadeIn(500);
};

function fixFiles(action, task_id) {
	$('#process_welcome_row').hide();
	var senddata = { 
		'action' : action,
		'task_id' : task_id
	};
	$('#process_working_row').load('/fixfiles', senddata).fadeIn(500);
}

function postProcess(action) {
	$('#process_welcome_row').hide();
	var senddata = { 
		'action' : action
	};
	$('#process_working_row').load('/postproc', senddata).fadeIn(500);
}

// function that finds all radio buttons on the page that are selected and returns their ID and value
function getRadioValues() {
	var radio_values = {};
	$('input[type=radio]:checked').each(function() {
		radio_values[$(this).attr('name')] = $(this).val();
	});
	//console.log(radio_values);
	return radio_values;
} 

function updateCustomDate(fileId) {
	var dateInput = document.getElementById('fileid_' + fileId + '_custom_date');
	var radioInput = document.getElementById('fileid_' + fileId + '_custom');
	radioInput.value = dateInput.value;
}

function setAllRadio(type) {
	var radios = document.querySelectorAll('.form-check-input');
	radios.forEach(function(radio) {
		if (type === 'ignore' && radio.value === 'ignore') {
			radio.checked = true;
		} else if (type === 'delete' && radio.value === 'delete') {
			radio.checked = true;
		} else if (type === 'custom' && radio.id.includes('_custom')) {
			radio.checked = true;
			var custom_date = document.getElementById('selectDateModalBulk');
			radio.value = custom_date.value;
			var update_date = document.getElementById(radio.id + '_date');
			update_date.value = custom_date.value;
		} else if (type === 'startdate' && radio.id.includes('_startdate')) {
			radio.checked = true;
		} else if (type === 'enddate' && radio.id.includes('_enddate')) {
			radio.checked = true;
		} else if (type === 'filedate' && radio.id.includes('_filedate')) {
			radio.checked = true;
		} else if (type === 'filename' && radio.id.includes('_filename')) {
			radio.checked = true;
		} else if (type === 'pathname' && radio.id.includes('_pathname')) {
			radio.checked = true;
		}
	});
}

function submitAllSelected() {
	var radio_values = getRadioValues();
	var task_id = document.getElementById('task_id').value;
	radio_values = JSON.stringify(radio_values);
	var senddata = {
		'action' : 'process',
		'radio_values' : radio_values,
		'task_id' : task_id
	};
	$('#process_working_row').load('/finish', senddata).fadeIn(500);
}

function showResultsPage(task_id) {
	var senddata = {
		'action' : 'results',
		'task_id' : task_id
	};
	$('#process_working_row').load('/finish', senddata).fadeIn(500);
}

function cancelAction(task_id) {
	var senddata = {
		'action' : 'cancel',
		'task_id' : task_id
	};
	$('#process_working_row').load('/cancel', senddata);
	window.location.replace('/');
}

// Select Originals to Process 
$('#process_postprocess_btn').click(function(){
	postProcess('start');
});

function preprocessFolder(action, folder_path) {
	$('#process_welcome_row').hide();

	//console.log('folder_path: ' + folder_path);

	var senddata = { 
		'action' : action,
		'folder_path' : folder_path,
	}; 
	$('#process_working_row').load('/preproc', senddata).fadeIn(500);
}

function toggleProcessed(pathID, path, flag) {
	console.log(pathID);
	console.log(path);
	console.log(flag);
	
	if (flag == 'True') {
		var toggled = false;
	} else {
		var toggled = true;
	}
	
	const post_data = {
		'path' : path,
		'flag' : toggled
	}

	// Ajax post to /toggle_processed
	$.ajax({
		type: 'POST',
		url: '/toggle_processed',
		data: JSON.stringify(post_data),
		contentType: 'application/json',
		success: function(response) {
			console.log('Success:', response);
			if (flag == 'False') {
				document.getElementById(pathID).innerHTML = '<i class="fa-solid fa-circle-check text-success"></i>';
				document.getElementById(pathID).setAttribute('value', 'True');
			} else {
				document.getElementById(pathID).innerHTML = '<i class="fa-solid fa-circle-xmark text-danger"></i>';
				document.getElementById(pathID).setAttribute('value', 'False');
			}
		},
		error: function(error) {
			console.error('Error:', error);
		}
	});
}