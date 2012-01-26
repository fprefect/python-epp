
clean:
	find . -name "*.pyc" -exec rm {} \;
	find . -name dropin.cache -exec rm {} \;
